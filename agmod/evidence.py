"""Typed symbol evidence passed from reverse engineering tools to code generation."""
from __future__ import annotations

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
    confidence: float = 1.0

    @property
    def full_class_name(self) -> str:
        if self.namespace and not self.class_name.startswith(self.namespace + "."):
            return f"{self.namespace}.{self.class_name}"
        return self.class_name

    def to_dict(self) -> dict:
        return asdict(self)

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
        confidence = float((data.get("evidence") or {}).get("confidence", target.get("confidence", 1.0)))
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
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
            evidence_source=str((data.get("evidence") or {}).get("source") or target.get("evidence_source") or ""),
            confidence=confidence,
        )
