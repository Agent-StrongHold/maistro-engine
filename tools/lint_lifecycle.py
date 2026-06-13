#!/usr/bin/env python3
"""Lifecycle status linter for ADRs and Specs (ADR-097)."""

import re
import sys
from pathlib import Path

import yaml

# ── Valid statuses ──────────────────────────────────────────────────────────

ADR_STATUSES = [
    "Proposed",
    "Deferred",
    "Denied",
    "Accepted",
    "Fully Specced",
    "Implemented",
    "Deprecated",
    "Superseded",
]

SPEC_STATUSES = [
    "Proposed",
    "Deferred",
    "Will Not Implement",
    "Accepted",
    "AC Defined",
    "In Progress",
    "Tests Passing",
    "Implemented",
    "Superseded",
]

# ── Valid transitions (forward-only) ───────────────────────────────────────

ADR_TRANSITIONS: dict[str, set[str]] = {
    "Proposed": {"Accepted", "Deferred", "Denied"},
    "Deferred": {"Accepted", "Denied"},
    "Accepted": {"Fully Specced", "Implemented", "Deprecated", "Superseded"},
    "Fully Specced": {"Implemented", "Deprecated", "Superseded"},
    "Implemented": {"Deprecated", "Superseded"},
    "Denied": set(),
    "Deprecated": set(),
    "Superseded": set(),
}

SPEC_TRANSITIONS: dict[str, set[str]] = {
    "Proposed": {"Accepted", "Deferred", "Will Not Implement"},
    "Deferred": {"Accepted", "Will Not Implement"},
    "Accepted": {"AC Defined", "In Progress", "Tests Passing", "Implemented", "Superseded"},
    "AC Defined": {"In Progress", "Tests Passing", "Implemented", "Superseded"},
    "In Progress": {"Tests Passing", "Implemented", "Superseded"},
    "Tests Passing": {"Implemented", "Superseded"},
    "Implemented": {"Superseded"},
    "Will Not Implement": set(),
    "Superseded": set(),
}

# ── Required fields per status ─────────────────────────────────────────────

ADR_REQUIRED: dict[str, list[str]] = {
    "Proposed": ["title", "created"],
    "Accepted": ["title", "created", "owners"],
    "Fully Specced": ["title", "created", "owners", "implements"],
    "Implemented": ["title", "created", "owners"],
    "Deferred": ["title", "created"],
    "Denied": ["title", "created"],
    "Deprecated": ["title", "created"],
    "Superseded": ["title", "created", "superseded-by"],
}

SPEC_REQUIRED: dict[str, list[str]] = {
    "Proposed": ["title", "created"],
    "Accepted": ["title", "created", "owners"],
    "AC Defined": ["title", "created", "owners"],
    "In Progress": ["title", "created", "owners"],
    "Tests Passing": ["title", "created", "owners", "tests"],
    "Implemented": ["title", "created", "owners", "tests"],
    "Deferred": ["title", "created"],
    "Will Not Implement": ["title", "created"],
    "Superseded": ["title", "created", "superseded-by"],
}

# ── Frontmatter parser ─────────────────────────────────────────────────────

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def parse_frontmatter(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    return yaml.safe_load(m.group(1))


def has_acceptance_criteria(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    idx = text.find("## Acceptance Criteria")
    if idx == -1:
        return False
    after = text[idx + len("## Acceptance Criteria") :].strip()
    # Non-empty if there's content before the next heading or EOF
    next_heading = after.find("\n## ")
    section = after[:next_heading] if next_heading != -1 else after
    return len(section.strip()) > 0


# ── Validation ─────────────────────────────────────────────────────────────


def lint_file(path: Path) -> list[str]:
    errors = []
    fm = parse_frontmatter(path)
    if fm is None:
        errors.append(f"{path}: no YAML frontmatter found")
        return errors

    kind = fm.get("kind", "")
    status = fm.get("status", "")

    if kind == "adr":
        valid_statuses, transitions, required = ADR_STATUSES, ADR_TRANSITIONS, ADR_REQUIRED
    elif kind == "spec":
        valid_statuses, transitions, required = SPEC_STATUSES, SPEC_TRANSITIONS, SPEC_REQUIRED
    else:
        # Skip non-adr/spec documents
        return errors

    # 1. Valid status
    if status not in valid_statuses:
        errors.append(f"{path}: invalid status '{status}' for kind '{kind}'")
        return errors

    # 2. Required fields
    for field in required.get(status, []):
        val = fm.get(field)
        if val is None or val == "" or val == []:
            errors.append(f"{path}: status '{status}' requires field '{field}'")

    # 3. AC section required for specs at AC Defined+
    if (
        kind == "spec"
        and status in ("AC Defined", "Tests Passing", "Implemented")
        and not has_acceptance_criteria(path)
    ):
        errors.append(
            f"{path}: status '{status}' requires non-empty '## Acceptance Criteria' section"
        )

    # 4. History validation
    errors.extend(lint_history(path, fm, status, valid_statuses, transitions))

    return errors


def reachable_from(start: str, transitions: dict[str, set[str]]) -> set[str]:
    """Transitive closure of forward transitions from `start`."""
    reachable: set[str] = set()
    frontier = [start]
    while frontier:
        node = frontier.pop()
        for nxt in transitions.get(node, set()):
            if nxt not in reachable:
                reachable.add(nxt)
                frontier.append(nxt)
    return reachable


def lint_history(
    path: Path,
    fm: dict,
    status: str,
    valid_statuses: list[str],
    transitions: dict[str, set[str]],
) -> list[str]:
    errors: list[str] = []
    history = fm.get("history")
    if not history or not isinstance(history, list):
        return errors

    prev = None
    for entry in history:
        cur = entry.get("status", "")
        if cur not in valid_statuses:
            errors.append(f"{path}: history contains invalid status '{cur}'")
            break
        # Forward-only: cur must be reachable from prev via transitive closure
        if prev and cur not in reachable_from(prev, transitions):
            errors.append(f"{path}: invalid transition '{prev}' → '{cur}' in history")
        prev = cur

    # Last history entry should match current status
    if history[-1].get("status") != status:
        errors.append(
            f"{path}: status '{status}' doesn't match last history entry "
            f"'{history[-1].get('status')}'"
        )

    return errors


# ── AC traceability ────────────────────────────────────────────────────────

AC_ID_RE = re.compile(r"\*\*AC-(\d+)\*\*")
MARKER_RE = re.compile(r'@pytest\.mark\.ac\(["\']([^"\']+)["\']\)')
PARAM_RE = re.compile(r'pytest\.mark\.ac\(["\']([^"\']+)["\']\)')


def extract_ac_ids(path: Path) -> list[str]:
    """Extract AC-N IDs from a spec's Acceptance Criteria section."""
    text = path.read_text(encoding="utf-8")
    idx = text.find("## Acceptance Criteria")
    if idx == -1:
        return []
    after = text[idx:]
    next_heading = after.find("\n## ", 1)
    section = after[:next_heading] if next_heading != -1 else after
    fm = parse_frontmatter(path)
    spec_id = fm.get("id", "") if fm else ""
    ids = []
    for m in AC_ID_RE.finditer(section):
        ids.append(f"{spec_id}/AC-{m.group(1)}")
    return ids


def scan_test_ac_markers(test_roots: list[str]) -> set[str]:
    """Scan all test files for @pytest.mark.ac("SPEC-NNN/AC-N") markers."""
    covered = set()
    for root in test_roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for path in root_path.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for m in MARKER_RE.finditer(text):
                covered.add(m.group(1))
            for m in PARAM_RE.finditer(text):
                covered.add(m.group(1))
    return covered


def check_ac_traceability(spec_roots: list[str], test_roots: list[str]) -> list[str]:
    """Check that every AC-N in specs at Tests Passing+ has a test with matching marker."""
    errors = []
    covered = scan_test_ac_markers(test_roots)

    for root in spec_roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for path in sorted(root_path.glob("SPEC-*.md")):
            fm = parse_frontmatter(path)
            if not fm:
                continue
            status = fm.get("status", "")
            if status not in ("Tests Passing", "Implemented"):
                continue
            ac_ids = extract_ac_ids(path)
            for ac_id in ac_ids:
                if ac_id not in covered:
                    errors.append(f'{path}: {ac_id} has no test with @pytest.mark.ac("{ac_id}")')
    return errors


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> int:
    roots = sys.argv[1:] or ["docs/adr", "docs/specs"]
    all_errors = []

    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for path in sorted(root_path.glob("*.md")):
            if not re.match(r"^(ADR|SPEC)-\d+", path.name):
                continue
            all_errors.extend(lint_file(path))

    # AC traceability (only for spec roots)
    spec_roots = [r for r in roots if "spec" in r]
    test_roots = [
        "packages/maistro-core/tests",
        "packages/maistro-server/tests",
        "packages/maistro-bootstrap/tests",
        "packages/maistro-evolve/tests",
        "packages/maistro-turing/tests",
        "packages/maistro-canvas/tests",
        "packages/maistro-design/tests",
        "packages/maistro-rsi/tests",
        "packages/hive-conductor/backend/tests",
        "tests",
    ]
    all_errors.extend(check_ac_traceability(spec_roots, test_roots))

    for err in all_errors:
        print(f"  ✗ {err}")

    if all_errors:
        print(f"\n{len(all_errors)} lifecycle error(s) found.")
        return 1

    print("✓ All documents pass lifecycle checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
