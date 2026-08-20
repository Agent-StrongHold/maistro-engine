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
    # Private key blocks.
    #
    # The body is base64-and-whitespace, not the unbounded lazy `[\s\S]*?` this
    # replaced. Two problems with the old form, both from unterminated BEGIN
    # markers: it scanned to end-of-input once per marker (quadratic — 136 ms at
    # 32 KB), and merely bounding the length did not fix it, since the bound
    # only bites once input exceeds it. Excluding `-` from the body is what
    # makes it linear: an unterminated block now fails at the first character of
    # the *next* `-----BEGIN` instead of scanning on. The length cap stays as a
    # backstop; 16 KiB is far above any real PEM (a 4096-bit RSA key is ~3.2 KB),
    # and a block exceeding it still has its base64 body caught by the
    # high-entropy pass — the label changes, the secret does not survive.
    (
        re.compile(
            r"-----BEGIN [A-Z ]{0,32}PRIVATE KEY-----[A-Za-z0-9+/=\s]{0,16384}?"
            r"-----END [A-Z ]{0,32}PRIVATE KEY-----"
        ),
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
    # Query params with secret-like names.
    #
    # `\w{0,64}`, not `\w*`: unbounded, both quantifiers scan the same character
    # class as the alternation, so every offset in a long word run rescans to
    # the end looking for `=`. `"?" + "api_key"*n` cost 682 ms at 32 KB and grew
    # 4x per doubling — quadratic. Bounding them makes per-offset work constant.
    # (`api_key` is dropped from the alternation: `key` already subsumes it.)
    (
        re.compile(r"[?&]\w{0,64}(?:secret|token|key|password)\w{0,64}=[^&\s]+", re.IGNORECASE),
        "[REDACTED_QUERY_PARAM]",
    ),
    # URL userinfo (user:pass@host).
    #
    # The `(?<!\w)` anchor is load-bearing for performance, not matching. Without
    # it `\w+` has no left edge, so `finditer` restarts inside every long word
    # run and rescans to its end hunting for `://`: `"_" * 32000` took 4.2 s in
    # this one pattern, and `redact()` sits on the logging hot path, so a single
    # base64 blob or long traceback frame in a log line stalled the logger for
    # seconds — reachable from untrusted content, no attacker required. Anchoring
    # is 3333x faster at 32 KB and linear thereafter.
    (
        re.compile(r"(?<!\w)\w+://[^\s/@:]+:[^\s@]+@[^\s]*"),
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
        # `""`, not `text`. The falsy short-circuit used to pass its argument
        # straight back, so `redact(None)` returned `None` — contradicting this
        # function's own `-> str` annotation and SPEC-223, which declares the
        # same signature twice. No caller can reach it (both call sites in
        # log_redaction.py are statically `str`), so this is a latent type lie
        # rather than live behaviour, and a redactor should fail closed anyway.
        return ""

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
