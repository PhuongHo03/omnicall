"""Credential detection/redaction used before persistence or diagnostics."""

from __future__ import annotations

import re
from typing import Any


_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"\bnvapi-[A-Za-z0-9_-]{16,}\b", re.IGNORECASE), "[REDACTED_NVIDIA_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"(?i)\b(password|passwd|api[_ -]?key|secret|token)\s*[:=]\s*([^\s,;]{6,})"), r"\1=[REDACTED]"),
)


def redact_secrets(value: str) -> tuple[str, bool]:
    redacted = value
    found = False
    for pattern, replacement in _SECRET_PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        found = found or count > 0
    return redacted, found


def redact_structure(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secrets(value)[0]
    if isinstance(value, list):
        return [redact_structure(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_structure(item) for item in value)
    if isinstance(value, dict):
        return {str(key): redact_structure(item) for key, item in value.items()}
    return value
