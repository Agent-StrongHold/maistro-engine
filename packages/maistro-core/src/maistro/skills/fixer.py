"""Security repair engine for marketplace skills and agents.

Attempts to automatically fix security issues found by the scanner.
Returns what was fixed, what couldn't be fixed, and the cleaned content.
"""

from __future__ import annotations

import re
import unicodedata


def fix_content(content: str) -> tuple[str, list[str], list[str]]:  # noqa: C901  pre-existing: long sequence of independent repair passes
    """Attempt to repair security issues in skill/agent content.

    Returns:
        (fixed_content, fixes_applied, unfixable_issues)
    """
    fixes: list[str] = []
    unfixable: list[str] = []
    fixed = content

    normalized = unicodedata.normalize("NFKD", fixed)
    if normalized != fixed:
        fixes.append(
            "Normalized unicode characters (NFKD) — removed directional markers and lookalikes"
        )
        fixed = normalized

    direction_markers = re.findall(
        r"[\u200b\u200c\u200d\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]", fixed
    )
    if direction_markers:
        fixed = re.sub(
            r"[\u200b\u200c\u200d\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]", "", fixed
        )
        fixes.append(f"Removed {len(direction_markers)} hidden unicode direction markers")

    exec_patterns = [
        (r"\bexec\s*\([^)]*\)", "exec() call"),
        (r"\beval\s*\([^)]*\)", "eval() call"),
        (r"\bsubprocess\.\w+\s*\([^)]*\)", "subprocess call"),
        (r"\bos\.system\s*\([^)]*\)", "os.system() call"),
        (r"__import__\s*\([^)]*\)", "__import__() call"),
        (r"\bcompile\s*\([^)]*\)", "compile() call"),
        (r"\bimportlib\.\w+", "importlib usage"),
        (r"__builtins__", "__builtins__ access"),
        (r"\bglobals\s*\(\s*\)", "globals() access"),
    ]
    for pattern, desc in exec_patterns:
        matches = re.findall(pattern, fixed, re.IGNORECASE)
        if matches:
            fixed = re.sub(pattern, f"# [REMOVED: {desc}]", fixed, flags=re.IGNORECASE)
            fixes.append(f"Removed {len(matches)} {desc}(s)")

    dangerous_imports = re.findall(
        r"^\s*(?:import|from)\s+(?:subprocess|os|sys|shutil|importlib|ctypes|socket)\b.*$",
        fixed,
        re.MULTILINE,
    )
    if dangerous_imports:
        for imp in dangerous_imports:
            fixed = fixed.replace(imp, "# [REMOVED: dangerous import]")
        fixes.append(f"Removed {len(dangerous_imports)} dangerous import statement(s)")

    cred_pattern = (
        r"(?:api_key|secret|password|token|secret_key|secret_token"
        r"|master_password|database_url)\s*=\s*[\"'][^\"']{8,}[\"']"
    )
    cred_matches = re.findall(cred_pattern, fixed, re.IGNORECASE)
    if cred_matches:
        fixed = re.sub(
            cred_pattern,
            "# [REMOVED: hardcoded credential — use environment variable]",
            fixed,
            flags=re.IGNORECASE,
        )
        fixes.append(
            f"Replaced {len(cred_matches)} hardcoded credential(s) with env var placeholders"
        )

    injection_phrases = [
        (
            r"ignore\s+(?:all\s+)?previous\s+(?:instructions?|rules?|prompts?|guidelines?)",
            "instruction override",
        ),
        (r"(?:new|override|replacement)\s+instructions?:", "instruction injection"),
        (
            r"you\s+are\s+now\s+(?:in\s+)?(?:developer|admin|unrestricted|jailbreak)\s+mode",
            "jailbreak attempt",
        ),
        (
            r"(?:disregard|forget|override)\s+(?:all\s+)?(?:safety|content|previous)\s+(?:guidelines?|restrictions?|policies?|rules?|instructions?|prompts?)",
            "safety bypass",
        ),
        (
            r"you\s+have\s+(?:no|full|unlimited)\s+(?:restrictions?|access|limitations?)",
            "restriction removal",
        ),
        (r"previous\s+restrictions?\s+(?:are\s+)?lifted", "restriction removal"),
        (r"system\s+prompt\s+override", "system prompt override"),
    ]
    for pattern, desc in injection_phrases:
        matches = re.findall(pattern, fixed, re.IGNORECASE)
        if matches:
            fixed = re.sub(pattern, f"[REMOVED: {desc}]", fixed, flags=re.IGNORECASE)
            fixes.append(f"Stripped {len(matches)} prompt injection phrase(s): {desc}")

    shell_cmds = re.findall(r"\b(?:curl|wget)\s+-[^\n]*https?://[^\s]+", fixed)
    if shell_cmds:
        for cmd in shell_cmds:
            fixed = fixed.replace(
                cmd, "# [REMOVED: external shell command — use approved HTTP client]"
            )
        fixes.append(f"Replaced {len(shell_cmds)} shell command(s) with safe alternatives")

    tier_claim = re.search(r'trust_tier:\s*["\']?(t[01])["\']?', fixed)
    if tier_claim:
        fixed = re.sub(r'trust_tier:\s*["\']?t[01]["\']?', "trust_tier: t2", fixed)
        fixes.append(f"Downgraded trust tier claim from {tier_claim.group(1)} to t2 (community)")

    lines = [
        ln.strip()
        for ln in fixed.split("\n")
        if ln.strip() and not ln.strip().startswith("#") and not ln.strip().startswith("---")
    ]
    if lines:
        instruction_keywords = {
            "must",
            "always",
            "never",
            "ignore",
            "override",
            "execute",
            "run",
            "access",
            "unrestricted",
        }
        instruction_lines = sum(
            1 for ln in lines if any(kw in ln.lower() for kw in instruction_keywords)
        )
        density = instruction_lines / len(lines) if lines else 0
        if density > 0.5:
            unfixable.append(
                f"Content is {density:.0%} instruction-heavy — likely entirely prompt injection"
            )

    if _count_meaningful_body_lines(fixed) < 2 and fixes:
        unfixable.append(
            "No meaningful content remaining after security fixes — skill is entirely malicious"
        )

    return fixed, fixes, unfixable


def _count_meaningful_body_lines(content: str) -> int:
    """Count meaningful body lines, i.e. lines AFTER the closing frontmatter fence.

    YAML frontmatter is delimited by a pair of "---" fences; lines inside it (and
    the fences themselves) must NOT count toward meaningful body, otherwise a
    fully-stripped malicious skill with valid frontmatter is wrongly judged to
    still have content. Blank lines and [REMOVED:...] markers never count.
    """
    seen_open_fence = False
    in_body = False
    count = 0
    for line in content.split("\n"):
        if line.strip() == "---":
            if not seen_open_fence:
                seen_open_fence = True
            elif not in_body:
                in_body = True
            else:
                # A "---" within the body is just content, not a fence.
                count += 1
            continue
        if in_body and line.strip() and "[REMOVED:" not in line:
            count += 1
    return count


def is_deeply_flawed(fixes: list[str], unfixable: list[str]) -> bool:
    """Determine if content is too damaged to repair.

    Deeply flawed if:
    - Any unfixable issues exist, OR
    - More than 5 distinct security fixes were needed
    """
    if unfixable:
        return True
    return len(fixes) > 5
