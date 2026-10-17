"""MCP 结果转换：保留来源，清洗秘密，区分查询失败与业务状态。"""
import json
import re
from app.tools.base import ToolResult

SENSITIVE_KEY = re.compile(r"(?i)^(?:password|passwd|api[_-]?key|authorization|cookie|secret|private[_-]?key|(?:access_|refresh_)?token)$")
ASSIGNMENT = re.compile(r"(?i)(\b(?:password|passwd|api[_-]?key|secret|(?:access_|refresh_)?token)\s*[=:]\s*)[^\s,;]+")
BEARER = re.compile(r"(?i)(?:authorization\s*:\s*)?bearer\s+[^\s,;]+")
PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)


def redact_text(text: str, secret_values=()) -> str:
    text = PRIVATE_KEY.sub("<REDACTED>", text)
    text = BEARER.sub("Bearer <REDACTED>", text)
    text = ASSIGNMENT.sub(r"\1<REDACTED>", text)
    for value in sorted(set(secret_values), key=len, reverse=True):
        if value:
            text = text.replace(value, "<REDACTED>")
    return text


def environment_secrets(env):
    """长值保守脱敏；敏感环境变量即使短也脱敏（如 PGPASSWORD）。"""
    return tuple(value for key, value in env.items() if value and
                 (len(value) >= 8 or re.search(r"(?i)password|passwd|secret|token|key|auth|cookie", key)))


def clean_value(value, secret_values=()):
    if isinstance(value, dict):
        return {key: "<REDACTED>" if SENSITIVE_KEY.fullmatch(str(key)) else clean_value(item, secret_values)
                for key, item in value.items()}
    if isinstance(value, list):
        return [clean_value(item, secret_values) for item in value]
    if isinstance(value, str):
        return redact_text(value, secret_values)
    return value


def normalize_mcp_result(raw, *, server_id: str, remote_name: str,
                         max_chars: int = 8000, secret_values=()) -> ToolResult:
    source = {"transport": "mcp", "server_id": server_id, "remote_name": remote_name}
    if raw.is_error:
        return ToolResult(status="error", data={"source": source}, error="外部工具执行失败")
    payload = raw.structured_content
    if payload is None:
        blocks = raw.content or []
        if any(block.type != "text" for block in blocks):
            return ToolResult(status="error", data={"source": source}, error="unsupported_content：仅支持 JSON 或文本")
        payload = {"text": "\n".join(block.text for block in blocks)} if blocks else None
    try:
        payload = clean_value(payload, secret_values)
        text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        return ToolResult(status="error", data={"source": source}, error="MCP 返回值不符合 JSON 契约")
    empty = payload is None or payload == [] or payload == {} or payload == ""
    if isinstance(payload, dict) and set(payload) == {"text"}:
        empty = not payload["text"].strip()
    status = "no_data" if empty or isinstance(payload, dict) and payload.get("status") == "no_data" else "success"
    data = {"source": source, "payload": payload}
    if len(json.dumps(data, ensure_ascii=False)) > max_chars:
        # 计算整个 data（含来源和转义）而不是仅计算 payload。
        payload = {"_truncated": True, "_original_chars": len(text), "_preview": ""}
        data["payload"] = payload
        lower, upper = 0, len(text)
        while lower < upper:
            middle = (lower + upper + 1) // 2
            payload["_preview"] = text[:middle]
            if len(json.dumps(data, ensure_ascii=False)) <= max_chars:
                lower = middle
            else:
                upper = middle - 1
        payload["_preview"] = text[:lower]
    return ToolResult(status=status, data=data)
