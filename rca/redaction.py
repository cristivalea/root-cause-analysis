"""Secrets never reach the interface, the saved revisions or the logs (final_project_steps.md, E8).

Everything a step of the investigation saves (its summary and its details) and every error saved on a
revision goes through redact(): API keys, bearer tokens, JWTs, passwords written as key=value and the
account id the model provider puts in its error messages are replaced by a marker. The data of the
investigation itself (incidents, logs, changes) holds no secret in this project; the rule protects
against what an error message or a model answer might carry.
"""

from __future__ import annotations

import re
from typing import Any

MARK = "[redacted]"
PATTERNS = [
    re.compile(r"\bgsk_[A-Za-z0-9]{16,}"),  # Groq
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),  # OpenAI-style keys (OpenRouter)
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),  # Google AI Studio (Gemini)
    re.compile(r"\blsv2_[A-Za-z0-9_]{16,}"),  # LangSmith
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),  # a JWT
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)\b(password|passwd|secret|api[_\-]?key|token)(\s*[=:]\s*)[^\s,;'\"]+"),
    re.compile(r"\borg_[A-Za-z0-9]{8,}"),  # the account of the model provider
]


def redact(value: Any) -> Any:
    """The value with every secret replaced: strings, and the strings inside lists, tuples and dicts."""
    if isinstance(value, str):
        for pattern in PATTERNS:
            value = pattern.sub(lambda match: f"{match.group(1)}{match.group(2)}{MARK}" if match.lastindex == 2
                                else MARK, value)
        return value
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(redact(item) for item in value)
    return value
