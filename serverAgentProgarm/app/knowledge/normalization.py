"""Deterministic normalization and redaction for recovery knowledge."""

import hashlib
import json
import re
from typing import Any


_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,]+"),
    re.compile(r"(?i)(\b(?:token|password|passwd|api[_-]?key|secret)\s*[=:]\s*)[^\s,]+"),
)
_RANDOM_ID = re.compile(r"\b(?:[a-f0-9]{16,}|[0-9a-f]{8}-[0-9a-f-]{27,})\b", re.I)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def redact_text(text: str, max_chars: int = 4000) -> str:
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(r"\1<REDACTED>", result)
    result = _RANDOM_ID.sub("<ID>", result)
    return result[:max_chars]


def build_occurrence_signature(fields: dict[str, Any]) -> str:
    return sha256_text(canonical_json(fields))


def search_tokens(text: str) -> list[str]:
    """Extract safe lexical terms; never pass raw user text to FTS MATCH."""
    tokens: list[str] = []
    for term in re.findall(r"[A-Za-z0-9_.:-]+|[\u4e00-\u9fff]+", text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", term):
            tokens.extend(
                [term] if len(term) == 1 else [term[index:index + 2] for index in range(len(term) - 1)]
            )
        elif term not in {"and", "or", "not"}:
            tokens.append(term)
    return tokens


def fts_query(text: str) -> str:
    terms = search_tokens(text)
    return " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
