"""Sentinel PII filter: scans text for leaked secrets and personal data.

Detects and redacts API keys, IP addresses, email addresses, JWT tokens,
database connection strings, and other sensitive patterns in tool results
before they reach the user.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class PIIMatch:
    pii_type: str
    value: str
    start: int
    end: int


_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_token", re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}")),
    ("github_token", re.compile(r"github_pat_[A-Za-z0-9_]{22,}")),
    ("gitlab_token", re.compile(r"glpat-[A-Za-z0-9_-]{20,}")),
    ("api_key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9_-]{20,}")),
    (
        "api_key",
        re.compile(
            r"""(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)"""
            r"""[\s]*[=:]\s*["']?[A-Za-z0-9_/+=.-]{16,}["']?""",
            re.IGNORECASE,
        ),
    ),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    (
        "connection_string",
        re.compile(
            r"(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://"
            r"[^\s\"'>{})]+",
            re.IGNORECASE,
        ),
    ),
    (
        "ip_address",
        re.compile(
            r"\b(?!127\.0\.0\.1\b)(?!0\.0\.0\.0\b)(?!255\.255\.255\.255\b)"
            r"(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        ),
    ),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    (
        "password",
        re.compile(
            r"""(?:password|passwd|pwd)[\s]*[=:]\s*["']?[^\s"']{8,}["']?""",
            re.IGNORECASE,
        ),
    ),
]


def scan_for_pii(text: str) -> list[PIIMatch]:
    normalized = unicodedata.normalize("NFKD", text)
    matches: list[PIIMatch] = []
    seen_ranges: list[tuple[int, int]] = []

    for pii_type, pattern in _PII_PATTERNS:
        for m in pattern.finditer(normalized):
            start, end = m.start(), m.end()
            if any(not (end <= s or start >= e) for s, e in seen_ranges):
                continue
            matches.append(
                PIIMatch(
                    pii_type=pii_type,
                    value=m.group(),
                    start=start,
                    end=end,
                )
            )
            seen_ranges.append((start, end))

    matches.sort(key=lambda x: x.start)
    return matches


def redact(text: str, matches: list[PIIMatch] | None = None) -> str:
    if matches is None:
        matches = scan_for_pii(text)

    if not matches:
        return text

    result = text
    for match in sorted(matches, key=lambda x: x.start, reverse=True):
        placeholder = f"[REDACTED:{match.pii_type}]"
        result = result[: match.start] + placeholder + result[match.end :]

    return result


def scan_and_redact(text: str) -> tuple[str, list[PIIMatch]]:
    matches = scan_for_pii(text)
    return redact(text, matches), matches
