"""Lightweight local Web UI server for game-mod-agent.

Zero external dependencies: uses Python standard library `http.server`
and `threading` to serve a modern responsive dashboard and RESTful JSON API.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional, Tuple

from agmod import codegen, doctor, llm, log_repair, logs, planning, process, registry, rollback, saves

logger = logging.getLogger("agmod.ui")

INDEX_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")


def _read_body_json(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    content_len = int(handler.headers.get("Content-Length", 0))
    if content_len == 0:
        return {}
    raw_data = handler.rfile.read(content_len)
    try:
        return json.loads(raw_data.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Invalid JSON body: {e}")


def _safe_path(p: str) -> str:
    """Resolve and normalize path to avoid empty string or traversal quirks."""
    if not p:
        return ""
    return os.path.abspath(os.path.expanduser(p))


class ModUIRequestHandler(BaseHTTPRequestHandler):
    """Handles static SPA delivery and REST API routing."""

    server_version = "AIModBuilderUI/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        if os.environ.get("AGMOD_DEBUG"):
            logger.info("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

    def _is_safe_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urllib.parse.urlparse(origin)
        return parsed.hostname in ("127.0.0.1", "localhost")

    def _apply_cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin and self._is_safe_origin():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Vary", "Origin")

    def _send_json(self, status_code: int, data: Dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._apply_cors_headers()
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self, status_code: int, html_content: str) -> None:
        payload = html_content.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        if not self._is_safe_origin():
            self.send_response(HTTPStatus.FORBIDDEN)
            self.end_headers()
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._apply_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        if not self._is_safe_origin():
            self._send_json(HTTPStatus.FORBIDDEN, {
                "success": False,
                "error": "Cross-origin request rejected: origin is not authorized."
            })
            return

        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/health":
            self._send_json(HTTPStatus.OK, {
                "success": True,
                "data": {
                    "status": "online",
                    "version": "1.0.0",
                    "pid": os.getpid(),
                    "platform": sys.platform,
                }
            })
            return

        if path == "/api/doctor":
            try:
                report = doctor.check_environment()
                self._send_json(HTTPStatus.OK, {
                    "success": True,
                    "data": {
                        "ready": report.get("ready", False),
                        "details": report,
                        "formatted": doctor.format_doctor_report(report),
                    }
                })
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                    "success": False,
                    "error": f"Doctor check failed: {e}"
                })
            return

        if path == "/api/llm/config":
            try:
                cfg = llm.load_config()
                self._send_json(HTTPStatus.OK, {
                    "success": True,
                    "data": {
                        "config": llm.public_config(cfg),
                        "presets": llm.PRESETS,
                    }
                })
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                    "success": False,
                    "error": f"Failed to load LLM config: {e}"
                })
            return

        # Static SPA Delivery
        if path in ("/", "/index.html", "/ui"):
            if os.path.exists(INDEX_HTML_PATH):
                with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
                    content = f.read()
                self._send_html(HTTPStatus.OK, content)
            else:
                self._send_html(HTTPStatus.NOT_FOUND, "<h1>Dashboard HTML not found.</h1>")
            return

        # Fallback for SPA routing
        if os.path.exists(INDEX_HTML_PATH):
            with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
                content = f.read()
            self._send_html(HTTPStatus.OK, content)
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Page not found")

    def do_POST(self) -> None:
        if not self._is_safe_origin():
            self._send_json(HTTPStatus.FORBIDDEN, {
                "success": False,
                "error": "Cross-origin request rejected: origin is not authorized."
            })
            return

        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        try:
            body = _read_body_json(self)
        except ValueError as e:
            self._send_json(HTTPStatus.BAD_REQUEST, {"success": False, "error": str(e)})
            return

        routes: Dict[str, Callable[[Dict[str, Any]], Tuple[int, Dict[str, Any]]]] = {
            "/api/detect": self._handle_detect,
            "/api/process": self._handle_process,
            "/api/plan": self._handle_plan,
            "/api/codegen/template": self._handle_codegen_template,
            "/api/codegen/evidence": self._handle_codegen_evidence,
            "/api/mods/list": self._handle_mods_list,
            "/api/mods/conflicts": self._handle_mods_conflicts,
            "/api/mods/uninstall": self._handle_mods_uninstall,
            "/api/mods/rollback": self._handle_mods_rollback,
            "/api/saves/list": self._handle_saves_list,
            "/api/saves/create": self._handle_saves_create,
            "/api/saves/restore": self._handle_saves_restore,
            "/api/logs/read": self._handle_logs_read,
            "/api/logs/diagnose": self._handle_logs_diagnose,
            "/api/llm/config": self._handle_llm_config_save,
            "/api/llm/test": self._handle_llm_test,
            "/api/llm/chat": self._handle_llm_chat,
        }

        handler_fn = routes.get(path)
        if handler_fn is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"success": False, "error": f"API route not found: {path}"})
            return

        try:
            status_code, resp_data = handler_fn(body)
            self._send_json(status_code, resp_data)
        except Exception as e:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                "success": False,
                "error": f"Internal error handling {path}: {str(e)}"
            })

    # --- API Route Handlers ---

    def _handle_detect(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        info = registry.detect_engine(game_dir)
        return HTTPStatus.OK, {"success": True, "data": info}

    def _handle_process(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        status = process.check_game_status(game_dir)
        return HTTPStatus.OK, {"success": True, "data": status}

    def _handle_plan(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        request_text = body.get("request", "").strip()
        project_dir = _safe_path(body.get("project_dir", ""))
        mod_id = body.get("mod_id", "").strip()
        mod_name = body.get("mod_name", "").strip()
        mod_version = body.get("mod_version", "1.0.0").strip()
        customizations = body.get("customizations")

        if not game_dir or not request_text:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir and request are required"}

        if not project_dir:
            project_dir = os.path.join(game_dir, "_mod_projects", mod_id or "new_mod")

        spec = planning.create_mod_plan(
            game_dir=game_dir,
            request=request_text,
            project_dir=project_dir,
            mod_id=mod_id,
            mod_name=mod_name,
            mod_version=mod_version,
            customizations=customizations,
        )
        return HTTPStatus.OK, {"success": True, "data": spec}

    def _handle_codegen_template(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        engine = body.get("engine", "")
        class_name = body.get("class_name", "")
        method_name = body.get("method_name", "")
        hook_type = body.get("hook_type", "prefix")
        return_type = body.get("return_type", "void")
        parameters = body.get("parameters", [])

        if not engine or not class_name or not method_name:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "engine, class_name, and method_name are required"}

        try:
            res = codegen.generate_hook_template(
                engine=engine,
                class_name=class_name,
                method_name=method_name,
                hook_type=hook_type,
                return_type=return_type,
                parameters=parameters,
            )
            return HTTPStatus.OK, {"success": True, "data": res}
        except ValueError as e:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": str(e)}

    def _handle_codegen_evidence(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        evidence = body.get("evidence")
        if not evidence or not isinstance(evidence, dict):
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "evidence object is required"}
        try:
            res = codegen.generate_hook_from_evidence(evidence)
            return HTTPStatus.OK, {"success": True, "data": res}
        except Exception as e:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": str(e)}

    def _handle_mods_list(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        installs = rollback.list_installs(game_dir)
        return HTTPStatus.OK, {"success": True, "data": installs}

    def _handle_mods_conflicts(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        incoming_files = body.get("incoming_files", [])
        conflicts = rollback.check_conflicts(game_dir, incoming_files)
        return HTTPStatus.OK, {"success": True, "data": conflicts}

    def _handle_mods_uninstall(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        mod_id = body.get("mod_id", "").strip()
        if not game_dir or not mod_id:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir and mod_id are required"}
        res = rollback.uninstall(game_dir, mod_id)
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_mods_rollback(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        res = rollback.rollback_all(game_dir)
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_saves_list(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        res = saves.list_save_backups(game_dir)
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_saves_create(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        tag = body.get("label") or body.get("tag") or "manual"
        custom_save_dir = body.get("custom_save_dir", "")
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        res = saves.create_save_backup(game_dir, tag=tag, custom_save_dir=custom_save_dir)
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_saves_restore(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        backup_id = body.get("backup_id", "").strip()
        if not game_dir or not backup_id:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir and backup_id are required"}
        res = saves.restore_save_backup(game_dir, backup_id)
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_logs_read(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        lines = int(body.get("lines", 100))
        res = logs.read_mod_logs(game_dir, tail_lines=lines)
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_logs_diagnose(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        log_text = body.get("log_text", "")
        res = log_repair.diagnose_runtime_error(log_text)
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_llm_config_save(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        try:
            saved = llm.save_config(body)
            return HTTPStatus.OK, {"success": True, "data": saved}
        except Exception as e:
            return HTTPStatus.INTERNAL_SERVER_ERROR, {"success": False, "error": str(e)}

    def _handle_llm_test(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        result = llm.test_connection(body if body else None)
        status_code = HTTPStatus.OK if result.get("success") else HTTPStatus.BAD_REQUEST
        return status_code, result

    def _handle_llm_chat(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        messages = body.get("messages", [])
        game_context = body.get("game_context")
        result = llm.chat_completion(messages=messages, game_context=game_context)
        status_code = HTTPStatus.OK if result.get("success") else HTTPStatus.BAD_REQUEST
        return status_code, result


class ModUIServer:
    """Encapsulates the threading HTTP server instance for the UI."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self, blocking: bool = False) -> str:
        """Start the server. Returns the server URL."""
        if self._server is not None:
            return self.url

        self._server = ThreadingHTTPServer((self.host, self.port), ModUIRequestHandler)
        if blocking:
            try:
                self._server.serve_forever()
            except KeyboardInterrupt:
                self.stop()
        else:
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()

        return self.url

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None


_global_server: Optional[ModUIServer] = None
_server_lock = threading.Lock()


def get_or_start_server(host: str = "127.0.0.1", port: int = 8765) -> Tuple[ModUIServer, str]:
    """Get active server or start a new background server."""
    global _global_server
    with _server_lock:
        if _global_server is None:
            srv = ModUIServer(host=host, port=port)
            url = srv.start(blocking=False)
            _global_server = srv
            return srv, url
        return _global_server, _global_server.url


def _open_browser_safely(url: str) -> None:
    """Safely open default browser with OS-specific fallback."""
    try:
        if sys.platform == "win32":
            os.system(f'start "" "{url}"')
        else:
            webbrowser.open(url)
    except Exception:
        try:
            webbrowser.open(url)
        except Exception:
            pass


def launch_ui(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> str:
    """Launch the Web UI dashboard and optionally open the default browser."""
    srv, url = get_or_start_server(host=host, port=port)
    if open_browser:
        _open_browser_safely(url)
    return url


def main() -> None:
    import argparse
    import json
    import urllib.request

    parser = argparse.ArgumentParser(description="AI Mod Builder Web Dashboard Server")
    parser.add_argument("--host", default="127.0.0.1", help="Binding host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default 8765)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    # Reconfigure stdout/stderr for clean utf-8 on Windows
    if sys.platform == "win32":
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # 1. Check if an active server is already running on this port
    target_port = args.port
    is_already_running = False
    try:
        req = urllib.request.Request(f"http://{args.host}:{target_port}/api/health")
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("success") and data.get("data", {}).get("status") == "online":
                is_already_running = True
    except Exception:
        pass

    if is_already_running:
        url = f"http://{args.host}:{target_port}"
        print(f"\n========================================================")
        print(f"  AI Mod Builder 服务已在后台运行中:")
        print(f"  --> {url}")
        print(f"========================================================\n")
        if not args.no_browser:
            print("正在唤起默认浏览器打开工作台...")
            _open_browser_safely(url)
        return

    # 2. Start server, automatically trying next available port if port is occupied
    srv = None
    url = ""
    for p in range(target_port, target_port + 20):
        try:
            candidate = ModUIServer(host=args.host, port=p)
            url = candidate.start(blocking=False)
            srv = candidate
            break
        except OSError:
            srv = None
            continue

    if srv is None:
        print(f"[错误] 无法在端口 {target_port} - {target_port + 20} 启动服务，所有候选端口均被占用。")
        sys.exit(1)

    print(f"\n========================================================")
    print(f"  AI Mod Builder 工作台已启动:")
    print(f"  --> {url}")
    print(f"========================================================\n")
    if not args.no_browser:
        _open_browser_safely(url)

    try:
        while True:
            threading.Event().wait(1.0)
    except KeyboardInterrupt:
        print("\nShutting down AI Mod Builder Dashboard...")
        srv.stop()


if __name__ == "__main__":
    main()
