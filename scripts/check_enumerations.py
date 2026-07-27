#!/usr/bin/env python3
"""Assert that hand-maintained security enumerations still cover the tree.

Why this exists
---------------
Four reviews in a row found the same defect in four different subsystems: a
control is an explicit list, it is written against the one case that motivated
it, the codebase grows, and the list silently stops covering the new surface.

  * `verify-wheel-imports.py` enumerated 33 modules by hand.
  * `SENSITIVE_PATH_PATTERNS` enumerated 10 paths, and did not include the files
    added by the very commit that created the surface it guards.
  * `_PROTECTED_OPS` enumerated 5 route prefixes, and did not include
    `/v1/harness` — arbitrary code execution — mounted in the same PR.

Each was one line from being correct, and each was found by a human reading the
diff. That does not scale, and it is not what humans are good at. Enumerations
rot; properties do not. This script turns each list into a property checked
against the actual tree.

It is deliberately a *ratchet*, not a pass/fail gate, because the honest count
today is large: ~30 mounted routers perform mutating requests with no scope
entry. A zero baseline would block every PR on pre-existing gaps and would be
switched off within a week. So:

  * A gap that is already in the baseline is reported and tolerated.
  * A gap that is *not* in the baseline fails the build.
  * A baseline entry that is no longer a gap ALSO fails the build, which is what
    stops the file from becoming a permanent allowlist. Fix a gap, delete its
    line.

Every tolerated gap is printed on every run. A gate whose coverage silently
shrinks reads exactly like one that passes.

Usage
-----
    python scripts/check_enumerations.py                  # check
    python scripts/check_enumerations.py --write-baseline  # accept current state
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO / "quality" / "enumeration-baseline.json"

# Directories whose contents form the containment surface of a self-modifying
# system: the sandbox, the policy/scope engines, the security scanners, the CI
# definitions that gate all of it, and the ratchet baselines those gates read.
# A diff touching any of these should escalate to adversarial review.
SENSITIVE_ROOTS = (
    "packages/maistro-core/src/maistro/security/",
    "packages/maistro-core/src/maistro/policy/",
    "packages/maistro-core/src/maistro/capabilities/providers/",
    "packages/maistro-core/src/maistro/tools/sandbox/",
    "packages/maistro-rsi/src/maistro_rsi/sandbox/",
    "packages/maistro-rsi/src/maistro_rsi/durable_runs/",
    ".github/workflows/",
    "quality/",
    "sbx/",
)

# maistro subpackages intentionally absent from CORE_PUBLIC_SURFACE, because they
# are gated behind extras: importing them from a bare install *should* fail, so
# listing them in the no-extras tier would make that tier fail by design. Both
# are still swept by the `all` tier, and `maistro.identity`'s guard is pinned by
# packages/maistro-core/tests/identity/test_extra_guard.py.
SURFACE_EXEMPT = {
    "maistro.cli": "typer/rich, behind the `tui` extra",
    "maistro.identity": "bip-utils/pynacl, behind the `identity` extra",
}

# Route prefixes that legitimately need no scope entry.
ROUTE_EXEMPT = {
    "/v1/auth": "login/register/elevate — the thing that establishes identity",
    "/v1/setup": "first-run bootstrap, public by design (see _PUBLIC_EXACT)",
}


@dataclass
class Gap:
    check: str
    item: str
    detail: str

    def key(self) -> str:
        return f"{self.check}::{self.item}"


# --- check A: mutating routes must carry a scope ---------------------------


def check_routes() -> tuple[list[Gap], str | None]:
    """Every mutating /v1/ route must resolve to a permission in _PROTECTED_OPS.

    Introspects the real FastAPI app rather than parsing decorators: the app is
    the authority on what is actually mounted, including routers mounted
    conditionally behind feature flags, and it reports the true method set.
    """
    backend = REPO / "packages" / "hive-conductor" / "backend"
    if not backend.is_dir():
        return [], "hive-conductor backend not present"

    # The backend imports sibling workspace packages that are not pip-installed
    # (pytest supplies them via `src` roots in pyproject.toml), so mirror that
    # here rather than requiring an editable install of all nine.
    for src_root in sorted((REPO / "packages").glob("*/src")):
        sys.path.insert(0, str(src_root))
    sys.path.insert(0, str(backend))
    os.environ.setdefault("CONDUCTOR_DATA_DIR", "/tmp/enum-check-data")
    try:
        from main import app  # type: ignore[import-not-found]
        from middleware.auth import _PROTECTED_OPS  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - reported, never swallowed
        # Deliberately not a silent skip: if this check cannot run, the build
        # should say so rather than print a green tick it has not earned.
        return [], f"could not import the app ({type(exc).__name__}: {exc})"

    uncovered = sorted(
        {
            f"{method} {path}"
            for path, method in _mutating_v1_routes(app.routes)
            if not _route_is_scoped(path, method, _PROTECTED_OPS)
        }
    )
    return [
        Gap("routes", item, "mutating route with no _PROTECTED_OPS entry") for item in uncovered
    ], None


_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _mutating_v1_routes(routes: object) -> list[tuple[str, str]]:
    """(path, method) for every mounted /v1/ route that changes state."""
    found: list[tuple[str, str]] = []
    for route in routes:  # type: ignore[union-attr]
        path = getattr(route, "path", None)
        if not path or not path.startswith("/v1/"):
            continue
        methods = getattr(route, "methods", None) or set()
        found.extend((path, method) for method in sorted(methods & _MUTATING_METHODS))
    return found


def _route_is_scoped(path: str, method: str, protected: dict[str, dict[str, str]]) -> bool:
    """True if this route needs no scope entry, or already resolves to one."""
    if path.endswith("/invoke"):
        return True  # documented exemption in _required_permission
    if any(path.startswith(prefix) for prefix in ROUTE_EXEMPT):
        return True
    return any(path.startswith(prefix) for prefix in protected.get(method, {}))


# --- check B: the sensitive-path list must cover the sensitive dirs --------


def check_sensitive_paths() -> tuple[list[Gap], str | None]:
    """Every file under a containment-surface directory must escalate.

    `SENSITIVE_PATH_PATTERNS` is matched by substring against paths from
    `git diff --name-only`, so a pattern covers a directory when it appears in
    every path beneath it.
    """
    src = REPO / "packages" / "maistro-rsi" / "src" / "maistro_rsi" / "quarantine.py"
    if not src.is_file():
        return [], "quarantine.py not present"

    sys.path.insert(0, str(REPO / "packages" / "maistro-rsi" / "src"))
    try:
        from maistro_rsi.quarantine import SENSITIVE_PATH_PATTERNS
    except Exception as exc:  # pragma: no cover
        return [], f"could not import quarantine ({type(exc).__name__}: {exc})"

    gaps: list[Gap] = []
    for root in SENSITIVE_ROOTS:
        root_dir = REPO / root
        if not root_dir.is_dir():
            continue
        # One representative path is enough: patterns are substrings, so if the
        # directory itself is unmatched every file under it is unmatched.
        probe = f"{root}__probe__.py"
        if not any(pattern in probe for pattern in SENSITIVE_PATH_PATTERNS):
            gaps.append(
                Gap(
                    "sensitive_paths",
                    root,
                    "containment-surface directory not matched by SENSITIVE_PATH_PATTERNS",
                )
            )
    return gaps, None


# --- check C: the documented public surface must be complete ---------------


def check_core_surface() -> tuple[list[Gap], str | None]:
    """Every importable maistro subpackage must be in CORE_PUBLIC_SURFACE.

    This is the check that would have caught `maistro.identity` being absent
    from the list in the script whose own docstring names it.
    """
    spec_path = REPO / "scripts" / "verify-wheel-imports.py"
    if not spec_path.is_file():
        return [], "verify-wheel-imports.py not present"

    surface = _literal_list(spec_path, "CORE_PUBLIC_SURFACE")
    if not surface:
        return [], "could not read CORE_PUBLIC_SURFACE from verify-wheel-imports.py"

    core_src = REPO / "packages" / "maistro-core" / "src" / "maistro"
    if not core_src.is_dir():
        return [], "maistro-core src not present"

    return [
        Gap("core_surface", name, "importable module absent from CORE_PUBLIC_SURFACE")
        for name in _importable_children(core_src, prefix="maistro")
        if name not in surface and name not in SURFACE_EXEMPT
    ], None


def _literal_list(path: Path, name: str) -> set[str]:
    """Read a module-level list literal by name, via AST.

    Parsed rather than imported or exec'd: the target is a CLI with module-level
    dataclasses, so executing it here would run unrelated code and couple this
    check to that file's imports.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return set(ast.literal_eval(node.value))
    return set()


def _importable_children(root: Path, *, prefix: str) -> list[str]:
    """Dotted names of the importable modules and subpackages directly under root."""
    names: list[str] = []
    for child in sorted(root.iterdir()):
        if child.name.startswith(("_", ".")):
            continue
        if child.is_dir():
            if (child / "__init__.py").is_file():
                names.append(f"{prefix}.{child.name}")
        elif child.suffix == ".py":
            names.append(f"{prefix}.{child.stem}")
    return names


CHECKS = {
    "routes": check_routes,
    "sensitive_paths": check_sensitive_paths,
    "core_surface": check_core_surface,
}


def load_baseline() -> dict[str, str]:
    if not BASELINE_PATH.is_file():
        return {}
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return dict(data.get("tolerated", {}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="record the current gaps as tolerated (review the diff before committing)",
    )
    args = parser.parse_args()

    all_gaps: list[Gap] = []
    unavailable: list[tuple[str, str]] = []
    for name, fn in CHECKS.items():
        gaps, reason = fn()
        if reason:
            unavailable.append((name, reason))
        all_gaps.extend(gaps)

    if args.write_baseline:
        return _write_baseline(all_gaps)

    baseline = load_baseline()
    current = {g.key(): g for g in all_gaps}
    new_gaps = [g for k, g in sorted(current.items()) if k not in baseline]
    fixed = sorted(k for k in baseline if k not in current)

    _report(baseline, current, unavailable, fixed, new_gaps)

    if new_gaps or fixed or unavailable:
        return 1
    print("\nno new enumeration gaps")
    return 0


def _write_baseline(all_gaps: list[Gap]) -> int:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_comment": (
            "Gaps in hand-maintained security enumerations that predate "
            "scripts/check_enumerations.py. This is a ratchet, not an "
            "allowlist: a NEW gap fails the build, and so does a stale "
            "entry here. Fix a gap, delete its line. Do not add entries "
            "without fixing or filing the underlying gap."
        ),
        "tolerated": {g.key(): g.detail for g in sorted(all_gaps, key=Gap.key)},
    }
    BASELINE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(all_gaps)} tolerated gaps to {BASELINE_PATH.relative_to(REPO)}")
    return 0


def _report(
    baseline: dict[str, str],
    current: dict[str, Gap],
    unavailable: list[tuple[str, str]],
    fixed: list[str],
    new_gaps: list[Gap],
) -> None:
    # Report what is tolerated, always. Silence here is how a shrinking gate
    # passes for a healthy one.
    if baseline:
        print(f"tolerated (baselined) gaps: {len(baseline) - len(fixed)}")
        for key in sorted(baseline):
            if key in current:
                print(f"  · {key}")

    if unavailable:
        print("\nCHECKS THAT COULD NOT RUN (treated as failure):")
        for name, reason in unavailable:
            print(f"  ! {name}: {reason}")

    if fixed:
        print(f"\nSTALE BASELINE ENTRIES ({len(fixed)}) — these are now covered:")
        for key in fixed:
            print(f"  ✓ {key}")
        print("Delete them from quality/enumeration-baseline.json to lock the fix in.")

    if new_gaps:
        print(f"\nNEW ENUMERATION GAPS ({len(new_gaps)}):")
        for gap in new_gaps:
            print(f"  ✗ [{gap.check}] {gap.item}\n      {gap.detail}")


if __name__ == "__main__":
    sys.exit(main())
