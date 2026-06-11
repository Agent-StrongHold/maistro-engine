"""CLI for the registry tool: walk + validate + lint + generate.

Usage:

    python -m maistro_registry.cli validate docs/adr/ADR-030.md
    python -m maistro_registry.cli walk .
    python -m maistro_registry.cli walk . --strict
    python -m maistro_registry.cli lint .
    python -m maistro_registry.cli lint . --strict
    python -m maistro_registry.cli generate .
    python -m maistro_registry.cli generate . --output registry/

No external CLI library: `argparse` from stdlib (no Click dep added).
Conforms to `engine#ADR-039` substrate posture.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

from maistro_registry.dag import Cycle, DuplicateId, find_cycles, find_duplicate_ids
from maistro_registry.generator import build_registry, write_registry
from maistro_registry.linker import (
    FilesystemResolver,
    LinkResult,
    check_links,
)
from maistro_registry.validator import ValidationResult, validate_file

# Walked file patterns. Order is for determinism, not precedence.
_WALK_PATTERNS: tuple[str, ...] = (
    "docs/adr/ADR-*.md",
    "docs/specs/**/*.md",
)


def _walk(root: Path) -> Iterable[Path]:
    seen: set[Path] = set()
    for pattern in _WALK_PATTERNS:
        for p in root.glob(pattern):
            # Skip scaffolding templates (e.g. ADR-000-template.md): they carry
            # placeholder ids/dates by design and are not real registry records.
            # Match the "-template.md" suffix precisely — a substring check on
            # "template" would wrongly skip real records like
            # ADR-033-templates-and-copier-workflow.md.
            if p.name.endswith("-template.md"):
                continue
            if p.suffix == ".md" and p.is_file() and p not in seen:
                seen.add(p)
                yield p


def _print_result(result: ValidationResult, *, quiet_ok: bool) -> None:
    if quiet_ok and result.ok and not result.warnings:
        return
    print(result.render())


def _exit_status(
    results: list[ValidationResult],
    *,
    strict: bool,
    quiet_ok: bool,
    extra_errors: int = 0,
) -> int:
    n_files = len(results)
    n_errors = sum(1 for r in results if r.errors)
    n_warnings = sum(1 for r in results if r.warnings)
    n_clean = n_files - n_errors - n_warnings

    for r in results:
        _print_result(r, quiet_ok=quiet_ok)

    print(
        f"\n{n_files} files checked: {n_clean} clean, "
        f"{n_errors} errors, {n_warnings} warnings, "
        f"{extra_errors} extra (DAG / dangling refs)",
        file=sys.stderr,
    )

    if n_errors or extra_errors:
        return 1
    if n_warnings and strict:
        return 1
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    files = [Path(f) for f in args.files]
    if not files:
        print("error: no files given", file=sys.stderr)
        return 2
    results = [validate_file(f) for f in files]
    return _exit_status(results, strict=args.strict, quiet_ok=args.quiet)


def cmd_walk(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    files = list(_walk(root))
    if not files:
        print(f"no candidate files found under {root}", file=sys.stderr)
        return 0

    results = [validate_file(f) for f in files]
    duplicates: list[DuplicateId] = find_duplicate_ids(results)
    for d in duplicates:
        print(f"  DUPLICATE: {d.render()}")

    return _exit_status(
        results, strict=args.strict, quiet_ok=args.quiet, extra_errors=len(duplicates)
    )


def cmd_lint(args: argparse.Namespace) -> int:
    """Walk + validate + DAG check + local link check."""
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    files = list(_walk(root))
    if not files:
        print(f"no candidate files found under {root}", file=sys.stderr)
        return 0

    results = [validate_file(f) for f in files]
    valid_fms = [r.front_matter for r in results if r.front_matter is not None]

    cycles: list[Cycle] = find_cycles(valid_fms, "supersedes") + find_cycles(valid_fms, "blocks")
    for c in cycles:
        print(f"  CYCLE: {c.render()}")

    resolver = FilesystemResolver(engine_root=root)
    link_results: list[LinkResult] = check_links(valid_fms, resolver)
    dangling = [lr for lr in link_results if not lr.resolved]
    for lr in dangling:
        print(f"  DANGLING: {lr.render()}")

    duplicates: list[DuplicateId] = find_duplicate_ids(results)
    for d in duplicates:
        print(f"  DUPLICATE: {d.render()}")

    extra = len(cycles) + len(dangling) + len(duplicates)
    return _exit_status(results, strict=args.strict, quiet_ok=args.quiet, extra_errors=extra)


def cmd_generate(args: argparse.Namespace) -> int:
    """Walk + validate + build registry + write registry.json/md.

    Skips files with errors but includes those with warnings (missing
    front-matter triggers a warning, not an error, during the rollout
    window per ADR-031 §6; those files are excluded from the registry
    body).
    """
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    files = list(_walk(root))
    if not files:
        print(f"no candidate files found under {root}", file=sys.stderr)
        return 0

    results = [validate_file(f) for f in files]
    valid_fms = [r.front_matter for r in results if r.front_matter is not None]
    n_errors = sum(1 for r in results if r.errors)

    if n_errors and not args.allow_errors:
        print(
            f"error: refusing to generate registry with {n_errors} errored files; "
            "pass --allow-errors to skip them and generate anyway",
            file=sys.stderr,
        )
        return 1

    registry = build_registry(valid_fms)
    out_dir = Path(args.output) if args.output else (root / "registry")
    json_path, md_path = write_registry(registry, out_dir)

    print(
        f"wrote {len(registry.entries)} entries to:\n  {json_path}\n  {md_path}",
        file=sys.stderr,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maistro-registry",
        description="ADR/spec front-matter registry tool (engine#engine-001).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as errors (post-rollout)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="only print failures",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="validate one or more files")
    p_val.add_argument("files", nargs="+", help="paths to ADR/spec markdown files")
    p_val.set_defaults(func=cmd_validate)

    p_walk = sub.add_parser("walk", help="walk a repo root and validate found files")
    p_walk.add_argument("root", nargs="?", default=".", help="repo root (default: cwd)")
    p_walk.set_defaults(func=cmd_walk)

    p_lint = sub.add_parser(
        "lint",
        help="walk + validate + DAG cycle check + local link check",
    )
    p_lint.add_argument("root", nargs="?", default=".", help="repo root (default: cwd)")
    p_lint.set_defaults(func=cmd_lint)

    p_gen = sub.add_parser(
        "generate",
        help="walk + validate + write registry.json + registry.md",
    )
    p_gen.add_argument("root", nargs="?", default=".", help="repo root (default: cwd)")
    p_gen.add_argument(
        "--output",
        "-o",
        help="output directory (default: <root>/registry)",
    )
    p_gen.add_argument(
        "--allow-errors",
        action="store_true",
        help="generate registry even if some files have validation errors",
    )
    p_gen.set_defaults(func=cmd_generate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
