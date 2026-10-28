"""Uniform responses, errors, parameter validation and the output budget (port of kb service/core.py;
api-contract §3, §4, §9)."""

import json
import re
import uuid

CONTRACT = "v1"
_HTTP = {"INVALID_PARAM": 400, "UNKNOWN_DOC": 404, "UNKNOWN_NODE": 404, "UNKNOWN_CONCEPT": 404,
         "LAYER_UNAVAILABLE": 409, "UNAUTHENTICATED": 401, "FORBIDDEN": 403, "NOT_FOUND": 404, "METHOD_NOT_ALLOWED": 405, "INTERNAL": 500}


class ApiError(Exception):
    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details

    @property
    def http_status(self) -> int:
        return _HTTP[self.code]

    def body(self) -> dict:
        return {"contract": CONTRACT, "error": {"code": self.code, "message": self.message, "details": self.details}}


def new_trace_id() -> uuid.UUID:
    return uuid.uuid4()


def envelope(tool: str, results: list, scope: dict, gaps: list, trace_id: uuid.UUID,
             truncated: bool = False, next_: dict | None = None, **extra) -> dict:
    out = {"contract": CONTRACT, "tool": tool, "results": results, "scope": scope, "gaps": gaps}
    out.update(extra)
    out.update({"truncated": truncated, "next": next_, "trace_id": f"tr_{trace_id.hex}"})
    return out


_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef]")


def estimate_tokens(obj, images: list[tuple[int, int]] = ()) -> int:
    """1 CJK character ~ 1 token, 4 other characters ~ 1 token, an image ~ width x height / 750 (compact JSON)."""
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)
    cjk = len(_CJK.findall(text))
    return cjk + (len(text) - cjk + 3) // 4 + sum(w * h // 750 for w, h in images)


def enum(params: dict, name: str, allowed: list, default):
    v = params.get(name, default)
    if v is None:
        v = default
    if v not in allowed:
        raise ApiError("INVALID_PARAM", f"{name} must be one of {allowed}", param=name, allowed=allowed)
    return v


def integer(params: dict, name: str, default, lo: int, hi: int):
    v = params.get(name, default)
    if v is None:
        return default
    if isinstance(v, str) and re.fullmatch(r"-?\d+", v):
        v = int(v)
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise ApiError("INVALID_PARAM", f"{name} must be an integer in [{lo}, {hi}]", param=name, allowed=[lo, hi])
    return v


def boolean(params: dict, name: str, default: bool) -> bool:
    v = params.get(name, default)
    if v is None:
        return default
    if isinstance(v, str) and v.lower() in ("true", "false", "1", "0"):
        return v.lower() in ("true", "1")
    if not isinstance(v, bool):
        raise ApiError("INVALID_PARAM", f"{name} must be a boolean", param=name, allowed=[True, False])
    return v


def string_list(params: dict, name: str) -> list[str] | None:
    v = params.get(name)
    if v is None:
        return None
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v):
        raise ApiError("INVALID_PARAM", f"{name} must be a list of strings", param=name, allowed="string[]")
    return list(dict.fromkeys(v))


def int_list(params: dict, name: str, lo: int, hi: int) -> list[int] | None:
    v = params.get(name)
    if v is None:
        return None
    if not isinstance(v, list):
        v = [v]
    out = []
    for x in v:
        if isinstance(x, str) and re.fullmatch(r"\d+", x):
            x = int(x)
        if isinstance(x, bool) or not isinstance(x, int) or not lo <= x <= hi:
            raise ApiError("INVALID_PARAM", f"{name} items must be integers in [{lo}, {hi}]", param=name,
                           allowed=[lo, hi])
        out.append(x)
    return sorted(set(out))


def reject_unknown(params: dict, known: set[str]) -> None:
    extra = sorted(set(params) - known)
    if extra:
        raise ApiError("INVALID_PARAM", f"unknown parameter(s): {extra}", param=extra[0], allowed=sorted(known))


def ignored_gap(name: str, why: str) -> dict:
    return {"code": "param_ignored", "param": name, "detail": f"{name} is ignored: {why}"}


# Gap severity: info = a hint that does not change conclusions; warn = may change them (the agent should say so).
GAP_SEVERITY = {"param_ignored": "info", "parallel_doc_available": "info", "concept_unknown": "info",
                "unlinked_text_only": "info", "restated": "info", "single_source": "info", "derived": "info"}


def with_severity(gaps: list[dict]) -> list[dict]:
    for g in gaps:
        g.setdefault("severity", GAP_SEVERITY.get(g["code"], "warn"))
    return gaps
