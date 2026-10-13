"""Regression tests for the stabilization pass."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod import logs, memory, pack, rea, repair, safety, updater
from agmod.paths import UnsafePathError, safe_extract_zip, safe_join
from agmod.planning import create_mod_plan, validate_project
from agmod.structures import fingerprint_files


class TestStability(unittest.TestCase):
    def test_scan_session_preserves_non_int_kind(self):
        session = memory.get_scan_session(4242, "float32")
        session.candidates = [0x1000]
        self.assertIs(session, memory.get_scan_session(4242))
        self.assertEqual(memory.get_scan_session(4242).kind, "float32")

    def test_fingerprint_sees_late_file_changes(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "game.dll")
            with open(path, "wb") as f:
                f.write(b"A" * 300000)
            first = fingerprint_files([path])
            with open(path, "r+b") as f:
                f.seek(299999)
                f.write(b"B")
            self.assertNotEqual(first, fingerprint_files([path]))

    def test_fingerprint_sees_middle_file_changes(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "game.pak")
            with open(path, "wb") as f:
                f.write(b"A" * 2_000_000)
            first = fingerprint_files([path])
            with open(path, "r+b") as f:
                f.seek(1_000_000)
                f.write(b"B")
            self.assertNotEqual(first, fingerprint_files([path]))

    def test_rea_uses_current_commands_without_shell(self):
        result = mock.Mock(returncode=0, stdout='{"ok": true}', stderr="")
        with mock.patch.object(rea, "_find_rea", return_value="rea"), mock.patch.object(rea.subprocess, "run", return_value=result) as run:
            rea.disassemble("game.exe", "Player::Update")
            args, kwargs = run.call_args
        self.assertEqual(args[0][:4], ["rea", "function", "game.exe", "Player::Update"])
        self.assertFalse(kwargs.get("shell", False))

    def test_rea_call_graph_uses_xrefs(self):
        result = mock.Mock(returncode=0, stdout="[]", stderr="")
        with mock.patch.object(rea, "_find_rea", return_value="rea"), mock.patch.object(rea.subprocess, "run", return_value=result) as run:
            rea.call_graph("game.exe", "Player::Update")
            args, _ = run.call_args
        self.assertEqual(args[0][:3], ["rea", "xrefs", "game.exe"])

    def test_build_diagnostics_report_non_cs_failure(self):
        result = repair.diagnose_build_output("NETSDK1004: Assets file not found.", return_code=1)
        self.assertTrue(result["has_errors"])
        self.assertEqual(result["errors"][0]["code"], "NETSDK1004")
        self.assertIn("Build failed", result["summary"])

    def test_update_rejects_traversal_and_non_exact_assets(self):
        with tempfile.TemporaryDirectory() as game:
            with self.assertRaises(ValueError):
                updater.update_mod(game, "owner", "repo", "../escape.dll")
            with mock.patch.object(updater, "latest_release", return_value={"assets": [{"name": "other.dll", "browser_download_url": "https://example.test/other"}]}):
                with self.assertRaises(RuntimeError):
                    updater.update_mod(game, "owner", "repo", "mod.dll")

    def test_update_downloads_exact_asset(self):
        with tempfile.TemporaryDirectory() as game:
            def download(url, dest):
                Path(dest).write_bytes(b"dll")
            with mock.patch.object(updater, "latest_release", return_value={"assets": [{"name": "mod.dll", "browser_download_url": "https://example.test/mod"}]}), mock.patch.object(updater.urllib.request, "urlretrieve", side_effect=download):
                dest = updater.update_mod(game, "owner", "repo", "mod.dll")
            self.assertTrue(os.path.isfile(dest))

    def test_package_requires_build_output(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "mod.json").write_text('{"id":"x","name":"X","version":"1.0.0","engine":"unity","entry":"x.dll"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                pack.package_mod(d)

    def test_package_includes_declared_dll(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "mod.json").write_text('{"id":"x","name":"X","version":"1.0.0","engine":"unity","entry":"x.dll"}', encoding="utf-8")
            out = Path(d, "out")
            out.mkdir()
            (out / "x.dll").write_bytes(b"dll")
            package = pack.package_mod(d)
            import zipfile
            with zipfile.ZipFile(package) as z:
                names = set(z.namelist())
            self.assertIn("x.dll", names)
            self.assertIn("manifest.json", names)

    def test_plan_creates_unreal_project_and_validates(self):
        with tempfile.TemporaryDirectory() as game, tempfile.TemporaryDirectory() as project:
            Path(game, "Game.uproject").write_text("{}", encoding="utf-8")
            spec = create_mod_plan(game, "增加一个可配置的测试功能", project, mod_name="测试 Mod", customizations={"amount": 3})
            self.assertEqual(spec["engine"]["id"], "unreal")
            self.assertTrue(Path(project, "MODDING_PLAN.md").is_file())
            self.assertTrue(Path(project, "scripts", "main.lua").is_file())
            self.assertTrue(validate_project(project)["ok"])

    def test_plan_prebuild_accepts_compiled_entry(self):
        with tempfile.TemporaryDirectory() as game, tempfile.TemporaryDirectory() as project:
            managed = Path(game, "Game_Data", "Managed")
            managed.mkdir(parents=True)
            (managed / "Assembly-CSharp.dll").write_bytes(b"")
            create_mod_plan(game, "增加金币", project, mod_id="demo-mod", mod_name="Demo")
            self.assertTrue(validate_project(project, stage="pre_build")["ok"])

    def test_plan_extracts_chinese_feature_terms(self):
        with tempfile.TemporaryDirectory() as game, tempfile.TemporaryDirectory() as project:
            Path(game, "Game.uproject").write_text("{}", encoding="utf-8")
            spec = create_mod_plan(game, "增加金币", project, mod_id="demo-mod", mod_name="Demo")
            self.assertIn("gold", spec["inspection_keywords"])

    def test_safe_zip_rejects_traversal(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            archive = os.path.join(d, "bad.zip")
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("../escape.txt", "bad")
            with self.assertRaises(UnsafePathError):
                safe_extract_zip(archive, os.path.join(d, "out"))

    def test_log_reader_ignores_symlinks_outside_game(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            target = Path(outside, "secret.log")
            target.write_text("SECRET", encoding="utf-8")
            Path(d, "BepInEx").mkdir()
            (Path(d, "BepInEx") / "LogOutput.log").symlink_to(target)
            self.assertFalse(logs.read_mod_logs(d)["found"])

    def test_safety_rejects_invalid_pid(self):
        self.assertFalse(safety.check_target(0)[0])

    def test_safe_join_rejects_escape(self):
        with self.assertRaises(UnsafePathError):
            safe_join("/tmp/base", "../outside")
        with self.assertRaises(UnsafePathError):
            safe_join("/tmp/base", "..\\outside")

    def test_unreal_install_rejects_traversal_id(self):
        from agmod.adapters.unreal import UnrealAdapter
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(UnsafePathError):
                UnrealAdapter().install_mod(d, d, "../escape")


if __name__ == "__main__":
    unittest.main(verbosity=2)
