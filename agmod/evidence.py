"""Typed symbol evidence passed from reverse engineering tools to code generation."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

_SUPPORTED_ENGINES = {"unity", "unreal", "re-engine", "godot"}
_ENGINE_ALIASES = {
    "ue4": "unreal",
    "ue5": "unreal",
    "reframework": "re-engine",
    "capcom": "re-engine",
    "godotmodloader": "godot",
}


@dataclass
class HookTarget:
    engine: str
    class_name: str
    method_name: str
    hook_type: str = "prefix"
    return_type: str = "void"
    parameters: list[dict] = field(default_factory=list)
    namespace: str = ""
    assembly: str = ""
    signature: str = ""
    overload_key: str = ""
    is_static: bool = False
    evidence_source: str = ""
    evidence_status: str = "suggested"
    verified: bool = False
    confidence: float = 1.0

    @property
    def full_class_name(self) -> str:
        if self.namespace and not self.class_name.startswith(self.namespace + "."):
            return f"{self.namespace}.{self.class_name}"
        return self.class_name

    def to_dict(self) -> dict:
        data = asdict(self)
        data["full_class_name"] = self.full_class_name
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "HookTarget":
        if not isinstance(data, dict):
            raise ValueError("symbol evidence must be an object")
        target = data.get("target", data)
        if not isinstance(target, dict):
            raise ValueError("evidence.target must be an object")
        engine = str(data.get("engine") or target.get("engine") or "").lower().strip()
        engine = _ENGINE_ALIASES.get(engine, engine)
        if engine not in _SUPPORTED_ENGINES:
            raise ValueError(f"unsupported engine '{engine}'")
        class_name = str(target.get("class_name") or target.get("class") or "").strip()
        method_name = str(target.get("method_name") or target.get("method") or "").strip()
        if not class_name or not method_name:
            raise ValueError("target.class_name and target.method_name are required")
        raw_params = target.get("parameters", [])
        if not isinstance(raw_params, list):
            raise ValueError("target.parameters must be an array")
        params = []
        for index, item in enumerate(raw_params):
            if not isinstance(item, dict):
                raise ValueError(f"parameter {index} must be an object")
            params.append({
                "name": str(item.get("name") or f"arg{index + 1}"),
                "type": str(item.get("type") or "object"),
            })
        hook_type = str(target.get("hook_type") or data.get("hook_type") or "prefix").lower()
        if hook_type not in {"prefix", "postfix", "both"}:
            raise ValueError("hook_type must be prefix, postfix, or both")
        evidence = data.get("evidence") or target.get("evidence") or {}
        confidence = float(evidence.get("confidence", target.get("confidence", 1.0)))
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        evidence_status = str(evidence.get("status") or target.get("evidence_status") or "suggested").lower()
        if evidence_status not in {"observed", "suggested", "verified", "manual", "unknown"}:
            raise ValueError("evidence.status must be observed, suggested, verified, manual, or unknown")
        verified = bool(evidence.get("verified", evidence_status == "verified"))
        return cls(
            engine=engine,
            class_name=class_name,
            method_name=method_name,
            hook_type=hook_type,
            return_type=str(target.get("return_type") or "void"),
            parameters=params,
            namespace=str(target.get("namespace") or ""),
            assembly=str(target.get("assembly") or ""),
            signature=str(target.get("signature") or ""),
            overload_key=str(target.get("overload_key") or ""),
            is_static=bool(target.get("is_static", False)),
            evidence_source=str(evidence.get("source") or data.get("provenance") or target.get("evidence_source") or ""),
            evidence_status=evidence_status,
            verified=verified,
            confidence=confidence,
        )


def _strip_symbol(raw: str) -> str:
    value = str(raw or "").strip().strip("`'\"")
    value = re.sub(r"^(?:function|method|symbol|member)\s+", "", value, flags=re.I)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _parameters(signature: str) -> list[dict]:
    match = re.search(r"\((.*)\)", signature, re.S)
    if not match or not match.group(1).strip():
        return []
    params = []
    for index, part in enumerate(match.group(1).split(",")):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if len(tokens) >= 2:
            params.append({"name": tokens[-1].strip("*&[]"), "type": " ".join(tokens[:-1])})
        else:
            params.append({"name": part.strip("*&[]"), "type": "object"})
    return params


def normalize_hook_target(
    raw: str | dict,
    engine_id: str,
    *,
    source: str = "",
    status: str = "observed",
    confidence: float = 0.65,
) -> dict | None:
    """Normalize common REA, UE4SS, REFramework and Cpp2IL symbol shapes."""
    if isinstance(raw, dict):
        symbol = raw.get("symbol") or raw.get("signature") or ""
        signature = str(raw.get("signature") or symbol)
        source = source or str(raw.get("source") or "")
        status = str(raw.get("status") or status or "observed")
        confidence = float(raw.get("confidence", confidence))
    else:
        symbol = str(raw or "")
        signature = symbol
    text = _strip_symbol(symbol)
    if not text:
        return None

    sdk_hook = re.search(r"""sdk\.hook\(\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]""", text, re.I)
    if sdk_hook:
        class_name, method_name = sdk_hook.group(1), sdk_hook.group(2)
    else:
        without_call = re.sub(r"\([^)]*\)", "", text, count=1).strip()
        without_call = re.sub(r"\b(?:public|private|protected|static|virtual|override|final)\b", "", without_call, flags=re.I).strip()
        if "::" in without_call:
            class_name, method_name = without_call.split("::", 1)
        elif ":" in without_call and not without_call.lower().startswith(("http:", "https:")):
            class_name, method_name = without_call.split(":", 1)
        elif "." in without_call:
            class_name, method_name = without_call.rsplit(".", 1)
        else:
            return None
        class_name = re.sub(r"^(?:function|type|class)\s+", "", class_name.strip(), flags=re.I)
        # Cpp2IL/REA signatures often prefix the declaring type with a return
        # type (`System.Void Game.Player.Controller::AddGold(...)`).
        class_name = class_name.split()[-1] if class_name.split() else class_name
        method_name = re.sub(r"[^A-Za-z0-9_].*$", "", method_name.strip())
    class_name = class_name.strip().strip("`'\"")
    method_name = method_name.strip().strip("`'\"")
    if not class_name or not method_name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", method_name):
        return None

    engine = _ENGINE_ALIASES.get(str(engine_id or "").lower(), str(engine_id or "").lower())
    if engine not in _SUPPORTED_ENGINES:
        return None
    namespace = ""
    if engine in {"unity", "godot"} and "." in class_name:
        namespace, class_name = class_name.rsplit(".", 1)
    return HookTarget(
        engine=engine,
        class_name=class_name,
        method_name=method_name,
        parameters=_parameters(signature),
        namespace=namespace,
        signature=signature[:500],
        evidence_source=source,
        evidence_status=status,
        verified=status == "verified",
        confidence=max(0.0, min(1.0, confidence)),
    ).to_dict()
