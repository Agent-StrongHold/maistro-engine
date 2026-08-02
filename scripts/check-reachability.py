#!/usr/bin/env python3
"""Fail when a new production module becomes unreachable from every entry point.

## Why this exists

This repo has repeatedly shipped correct, fully-tested modules that nothing in a
running system ever calls, behind documents saying they run:

* #344 — `tick_decay()` was tested and inert; memory never decayed.
* #346 — five specified security controls had no construction site.
* #347 — `POST /v1/skills/scan` returned `{"findings": [], "status": "clean"}`.
* SPEC-223 / ADR-064 — `redact()` had zero callers for its entire life while
  SECURITY.md said it scrubbed logs and COMPLIANCE.md cited it under EU AI Act
  Art. 10 and SOC 2.

Every one was found by audit, months late. Grepping for the symbol finds the
module, its tests, and the docs — everything except a caller — so the usual
review reflex actively confirms the wrong answer. Coverage does not catch it
either: these modules have *good* unit coverage. That is the point. The tests
are the only caller.

Vulture (already a gate here) works at symbol granularity within a file and
cannot see this: every function in an unreachable module is called by its
siblings and its tests, so the module is locally perfectly alive.

## What it does

Builds a module-level import graph over production code, roots it at the real
entry points, and ratchets the unreachable set against a reviewed baseline.
Being unreachable is not itself an error — `maistro-core` is a published library
and much of it is legitimately for importers, `maistro.testing` is scaffolding.
The error is *newly* unreachable code, which is almost always a subsystem that
was built and never wired.

Removals are reported, not failed, and the baseline should shrink over time.

## What it does NOT catch

The inverse, which is likelier and worse: a module that **is** reachable but
whose advertised capability is not. #346's `Sentinel` is constructed on a live
path — with `elevation_store=None`, so `policy.py` returns `None` and the whole
elevation ladder is inert. No import graph sees that. Reachability is a floor,
not a proof.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "quality" / "reachability-baseline.json"

# Real process entry points. `main` is the Conductor's `backend/main.py`; the
# rest are console scripts and ASGI targets.
STATIC_ROOTS = (
    "main",
    "maistro_server.main",
    "maistro.cli",
    "maistro_registry.cli",
    "maistro_rsi.cli",
    "maistro_bootstrap",
)

# Modules reached only through a runtime string — `import_module("routes.canvas")`
# in `main.py`'s optional-router loop and lifespan hooks. A static graph cannot
# see these, and omitting them would report large live subsystems as dead.
# Keep in sync with `_include_optional_router` calls and `lifespan` in main.py.
DYNAMIC_ROOTS = (
    "routes.canvas",
    "routes.pm_fleet_v2",
    "routes.evolution",
    "routes.rsi",
    "routes.daily_report_v2",
    "services.design_service",
    "services.design_preview",
    "services.design_render",
    "services.evolution",
    "services.scheduler",
    "services.memory_decay",
    "services.dag_run_store",
    "maistro_rsi.__main__",
    "maistro_turing.runtime",
    "maistro_canvas.canvas.routes",
)


def _collect_modules() -> dict[str, Path]:
    """module name → file, for every production module."""
    mods: dict[str, Path] = {}

    def add_tree(base: Path, prefix: str) -> None:
        for f in base.rglob("*.py"):
            parts = list(f.relative_to(base).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            name = ".".join(([prefix] if prefix else []) + parts)
            if name:
                mods[name] = f

    for src in sorted(ROOT.glob("packages/*/src")):
        for pkg in sorted(src.iterdir()):
            if pkg.is_dir() and (pkg / "__init__.py").exists():
                add_tree(pkg, pkg.name)
    # hive-conductor's backend is a flat layout resolved by sys.path, not a package.
    add_tree(ROOT / "packages/hive-conductor/backend", "")

    return {
        name: path
        for name, path in mods.items()
        if "/tests/" not in path.as_posix() and not path.name.startswith("test_")
    }


def _imports(path: Path, selfmod: str) -> set[str]:
    try:
        tree = ast.parse(path.read_text(errors="replace"))
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                own = selfmod.split(".")
                # `__init__.py` IS its package; any other module is one level down.
                pkg = own if path.name == "__init__.py" else own[:-1]
                up = node.level - 1
                pkg = pkg[: len(pkg) - up] if up else pkg
                base = ".".join(pkg + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            # `from x import y` may import module `x.y` or attribute `y` — record
            # both and let resolution pick the longest prefix that is a module.
            out.update(f"{base}.{a.name}" if base else a.name for a in node.names)
            out.add(base)
    return out


def _resolve(name: str, mods: dict[str, Path]) -> str | None:
    parts = name.split(".")
    while parts:
        cand = ".".join(parts)
        if cand in mods:
            return cand
        parts.pop()
    return None


def unreachable_modules() -> tuple[list[str], int]:
    mods = _collect_modules()
    edges = {
        name: {r for i in _imports(path, name) if (r := _resolve(i, mods)) and r != name}
        for name, path in mods.items()
    }

    stack = [r for r in (*STATIC_ROOTS, *DYNAMIC_ROOTS) if r in mods]
    seen: set[str] = set()
    while stack:
        mod = stack.pop()
        if mod in seen:
            continue
        seen.add(mod)
        stack.extend(edges.get(mod, ()))
        # Importing `a.b.c` executes `a/__init__.py` and `a/b/__init__.py`, so
        # whatever those import is reached too. Propagating after the traversal
        # instead marks the ancestors seen without ever following their edges,
        # which reports large live subsystems as dead.
        parts = mod.split(".")
        stack.extend(a for i in range(1, len(parts)) if (a := ".".join(parts[:i])) in mods)

    return sorted(set(mods) - seen), len(mods)


def main() -> int:
    unreachable, total = unreachable_modules()
    baseline = set(json.loads(BASELINE.read_text())["unreachable"])

    added = sorted(set(unreachable) - baseline)
    removed = sorted(baseline - set(unreachable))

    print(f"{total} production modules, {len(unreachable)} unreachable from any entry point")

    if removed:
        print(f"\n{len(removed)} module(s) newly REACHABLE — drop them from the baseline:")
        for mod in removed:
            print(f"  - {mod}")

    if not added:
        print("\nNo newly-unreachable modules.")
        return 0

    print(f"\n{len(added)} module(s) are NEWLY UNREACHABLE:\n")
    for mod in added:
        print(f"  {mod}")
    print(
        "\nNothing that runs imports these. If that is intended — a library-only\n"
        "surface, or test scaffolding — add them to quality/reachability-baseline.json\n"
        "with a note. If it is not, they are built-but-never-wired: give them a call\n"
        "path, and check that no doc already claims they run."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
