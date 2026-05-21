"""Secret redaction for logs, prompts, and error messages.

Compiles all regex patterns at import time. Patterns are applied in order
from most specific to least specific to avoid nested-pattern issues.
"""

from __future__ import annotations

import re

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        re.compile(r"(?:postgres|mysql|mongodb)://[^\s@/:]+:[^\s@]+@[^\s]*"),
        "[REDACTED_DB_CONNECTION]",
    ),
    (
        re.compile(r"(?:Bearer|Basic|Token)\s+\S+", re.IGNORECASE),
        "[REDACTED_AUTH_HEADER]",
    ),
    (
        re.compile(r"(?m)^(?:SECRET_KEY|API_KEY|PASSWORD)\s*=\s*\S+", re.IGNORECASE),
        "[REDACTED_ENV]",
    ),
    (
        re.compile(r"[?&]\w*(?:secret|token|key|api)\w*=[^&\s]+", re.IGNORECASE),
        "[REDACTED_QUERY_PARAM]",
    ),
    (
        re.compile(r"\w+://[^\s/@:]+:[^\s@]+@[^\s]*"),
        "[REDACTED_URL_USERINFO]",
    ),
    (
        re.compile(r"AKIA[A-Z0-9]{16}"),
        "[REDACTED_AWS_KEY]",
    ),
    (
        re.compile(r"eyJ[A-Za-z0-9_-]{47,}"),
        "[REDACTED_JWT]",
    ),
    (
        re.compile(
            r"(?:sk-ant-|sk_live_|sk_test_|sk-|ghp_|AIza|xoxb-|pplx-)[A-Za-z0-9_-]+"
        ),
        "[REDACTED_API_KEY]",
    ),
]


def redact(text: str) -> str:
    if not text:
        return text
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
