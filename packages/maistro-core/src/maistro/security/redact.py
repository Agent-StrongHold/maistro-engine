"""Secret redaction for logs, prompts, and error messages.

Fixes over the previous implementation:
- Auth-header pattern anchored to actual header context (not bare prose)
- Entropy heuristic catches unknown key formats (fail-closed)
- All match spans collected first, merged, then substituted once
  (no order-dependent overlaps leaving partial fragments)
"""

from __future__ import annotations

import math
import re
from collections import Counter

# ─── Patterns (order doesn't matter — we merge spans) ─────────────────────────

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Private keys
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        "[REDACTED_PRIVATE_KEY]",
    ),
    # DB connection strings
    (
        re.compile(r"(?:postgres|mysql|mongodb|redis)://[^\s@/:]+:[^\s@]+@[^\s]*"),
        "[REDACTED_DB_CONNECTION]",
    ),
    # Auth headers — ANCHORED to header context (fix #9: no longer matches prose)
    (
        re.compile(
            r"(?:^|[\r\n])(?:Authorization|X-Api-Key|X-Auth-Token)\s*[:=]\s*\S+",
            re.IGNORECASE | re.MULTILINE,
        ),
        "[REDACTED_AUTH_HEADER]",
    ),
    # Bearer/Basic/Token ONLY when preceded by colon/equals (header assignment context)
    (
        re.compile(r"(?:[:=]\s?)(?:Bearer|Basic|Token)\s+[A-Za-z0-9._+/=_-]{10,}", re.IGNORECASE),
        "[REDACTED_AUTH_HEADER]",
    ),
    # Env-var assignments
    (
        re.compile(r"(?m)^(?:SECRET_KEY|API_KEY|PASSWORD|PRIVATE_KEY)\s*=\s*\S+", re.IGNORECASE),
        "[REDACTED_ENV]",
    ),
    # Query params with secret-like names
    (
        re.compile(r"[?&]\w*(?:secret|token|key|api_key|password)\w*=[^&\s]+", re.IGNORECASE),
        "[REDACTED_QUERY_PARAM]",
    ),
    # URL userinfo (user:pass@host)
    (
        re.compile(r"\w+://[^\s/@:]+:[^\s@]+@[^\s]*"),
        "[REDACTED_URL_USERINFO]",
    ),
    # AWS access keys
    (
        re.compile(r"AKIA[A-Z0-9]{16}"),
        "[REDACTED_AWS_KEY]",
    ),
    # JWTs (3 base64url segments separated by dots)
    (
        re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
        "[REDACTED_JWT]",
    ),
    # Known API key prefixes
    (
        re.compile(
            r"(?:sk-ant-|sk_live_|sk_test_|sk-|ghp_|ghs_|github_pat_|AIza|xoxb-|xoxp-|pplx-|glpat-|ATATT)[A-Za-z0-9_-]{10,}"
        ),
        "[REDACTED_API_KEY]",
    ),
]

# ─── Entropy heuristic for unknown key formats (fix #9: fail-closed) ──────────

_HIGH_ENTROPY_RE = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{32,}(?![A-Za-z0-9_-])")


def _shannon_entropy(s: str) -> float:
    """Shannon entropy in bits per character."""
    if not s:
        return 0.0
    counts = Counter(s)
    length = len(s)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def _looks_like_secret(s: str) -> bool:
    """Heuristic: high entropy + mixed case + digits = likely a secret."""
    if len(s) < 32:
        return False
    entropy = _shannon_entropy(s)
    has_upper = any(c.isupper() for c in s)
    has_lower = any(c.islower() for c in s)
    has_digit = any(c.isdigit() for c in s)
    # Entropy > 4.0 bits/char with mixed charset = almost certainly a key
    return entropy > 4.0 and has_upper and has_lower and has_digit


# ─── Merge-spans redaction (fix #10: no order-dependent overlaps) ─────────────


def redact(text: str) -> str:  # noqa: C901  pre-existing: sequence of independent pattern passes
    """Redact all secrets from text using span-merging (no partial fragments)."""
    if not text:
        return text

    # Collect all (start, end, replacement) spans
    spans: list[tuple[int, int, str]] = []

    for pattern, replacement in _PATTERNS:
        for m in pattern.finditer(text):
            spans.append((m.start(), m.end(), replacement))

    # Entropy heuristic: catch unknown key formats
    for m in _HIGH_ENTROPY_RE.finditer(text):
        candidate = m.group()
        if _looks_like_secret(candidate):
            spans.append((m.start(), m.end(), "[REDACTED_HIGH_ENTROPY]"))

    if not spans:
        return text

    # Sort by start position, then by length descending (longer match wins)
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))

    # Merge overlapping spans (longest match at each position wins)
    merged: list[tuple[int, int, str]] = []
    for start, end, repl in spans:
        if merged and start < merged[-1][1]:
            # Overlaps with previous — keep the one that covers more
            prev_start, prev_end, prev_repl = merged[-1]
            if end > prev_end:
                merged[-1] = (prev_start, end, prev_repl)
            # Otherwise skip (already covered by previous longer match)
        else:
            merged.append((start, end, repl))

    # Build result in one pass (no sequential re.sub mutations)
    parts: list[str] = []
    cursor = 0
    for start, end, repl in merged:
        if start > cursor:
            parts.append(text[cursor:start])
        parts.append(repl)
        cursor = end
    parts.append(text[cursor:])

    return "".join(parts)
