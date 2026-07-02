"""`python -m maistro_rsi` — run a safe, capped, local self-improvement loop.

Drives the native builders agent (the engine behind `maistro builders`) to
propose improvements to a *clone* of a repo, gates each on the repo's own test
command, and ratchets forward only the ones that pass. Nothing is pushed and
the source checkout is never touched.

Example:
    python -m maistro_rsi run \\
        --repo C:/maistro \\
        --test-cmd "python -m pytest packages/maistro-core/tests -q" \\
        --cycles 3
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from maistro_rsi.competitors import parse_competitors
from maistro_rsi.local_loop import LocalRsiConfig, LocalRsiLoop


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="maistro_rsi", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a capped local self-improvement loop.")
    run.add_argument(
        "--repo", required=True, help="Path to the repo to improve (cloned, not touched)."
    )
    run.add_argument(
        "--test-cmd",
        required=True,
        help="Shell command that passes (exit 0) iff the repo is healthy.",
    )
    run.add_argument("--cycles", type=int, default=3, help="Hard cap on cycles (default: 3).")
    run.add_argument(
        "--objective", default=None, help="Override the improvement objective handed to the agent."
    )
    run.add_argument(
        "--targets",
        default=None,
        help="Comma-separated file paths to improve, one per cycle (rotated). "
        "Each cycle gets a targeted objective naming its file (overrides --objective).",
    )
    run.add_argument(
        "--model",
        default=None,
        help="LiteLLM model alias (default: MAISTRO_BUILDERS_MODEL / DEFAULT_MODEL).",
    )
    run.add_argument(
        "--agent-turns", type=int, default=6, help="Max agent turns per cycle (default: 6)."
    )
    run.add_argument(
        "--isolation",
        choices=("local", "container"),
        default="local",
        help="Where the agent runs: 'local' (host worktree) or 'container' "
        "(ADR-093 Docker isolation). Default: local.",
    )
    run.add_argument(
        "--image",
        default="maistro-builders:latest",
        help="Container image for --isolation container (default: maistro-builders:latest).",
    )
    run.add_argument(
        "--fitness",
        action="store_true",
        help="Decide promotion with the full multi-signal Scorecard (gates + weighted "
        "scores) instead of the bare test command; logs an auditable breakdown per cycle.",
    )
    run.add_argument(
        "--coverage-source",
        default=".",
        help="Path passed to coverage --source when --fitness is on (default: .).",
    )
    run.add_argument(
        "--coverage-pytest-args",
        default="",
        help="pytest args for the coverage run when --fitness is on (e.g. a scoped "
        "test path). Default: bare pytest, which runs every testpath in the repo.",
    )
    run.add_argument(
        "--competitors",
        default="",
        help="Tournament roster: 'model@temp,model,...' (e.g. "
        "'devstral-medium@0.2,codestral@0.7'). Each competes per target; the "
        "highest-scoring fix wins, complementary fixes are both kept. Empty ⇒ a "
        "single attempt with --model.",
    )
    run.add_argument(
        "--scout",
        action="store_true",
        help="Before competing, one model reads the target file and names the "
        "concrete improvement all competitors then implement (fairer head-to-head).",
    )
    run.add_argument(
        "--scout-model",
        default=None,
        help="Model alias for the scout (default: --model).",
    )
    run.add_argument(
        "--export-patches",
        default=None,
        help="After the run, export each promotion as a patch + manifest.json here "
        "(the durable output of an isolated run; feed to `maistro_rsi harvest`).",
    )
    run.add_argument(
        "--work-root",
        default=None,
        help="Where to put throwaway clones/worktrees (default: a temp dir).",
    )

    harvest = sub.add_parser(
        "harvest",
        help="Open PRs from an exported run, grouped by the file each promotion edited.",
    )
    harvest.add_argument(
        "--export-dir", required=True, help="Directory written by `run --export-patches`."
    )
    harvest.add_argument(
        "--repo-dir", required=True, help="Local checkout to build the PR branches in."
    )
    harvest.add_argument(
        "--base", default=None, help="Branch to base the PR branches on (default: current branch)."
    )
    harvest.add_argument(
        "--pr-base", default="main", help="Target branch for the PRs (default: main)."
    )
    harvest.add_argument(
        "--session", default=None, help="Session slug for branch names (default: a UTC timestamp)."
    )
    harvest.add_argument(
        "--push",
        action="store_true",
        help="Push branches and open PRs via gh (default: dry-run — build branches locally only).",
    )
    return parser


def _harvest(args: argparse.Namespace) -> int:
    import subprocess
    from datetime import UTC, datetime

    from maistro_rsi.harvest import branch_slug, group_by_file, load_manifest, pr_body, pr_title

    export = Path(args.export_dir)
    manifest = export / "manifest.json"
    if not manifest.is_file():
        print(f"error: no manifest.json in {export}", file=sys.stderr)
        return 2
    groups = group_by_file(load_manifest(manifest))
    if not groups:
        print("no promotions to harvest")
        return 0
    repo = str(Path(args.repo_dir).resolve())
    session = args.session or datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    def git(*a: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", "-C", repo, *a], check=check, capture_output=True, text=True)

    base = args.base or git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    opened = 0
    for file, group in groups.items():
        branch = branch_slug(file, session)
        git("checkout", "-B", branch, base)
        for patch in group:
            git("am", str((export / patch.patch_file).resolve()))
        action = "pushed + PR" if args.push else "built (dry-run)"
        print(f"[{action}] {branch}  <- {file}  ({len(group)} commit(s))")
        if args.push:
            git("push", "-u", "origin", branch, "--force-with-lease")
            subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--base",
                    args.pr_base,
                    "--head",
                    branch,
                    "--title",
                    pr_title(file, group),
                    "--body",
                    pr_body(file, group),
                ],
                cwd=repo,
                check=True,
            )
            opened += 1
    git("checkout", base, check=False)
    print(f"\nharvest: {len(groups)} file group(s), {opened} PR(s) opened")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "run":
        repo = Path(args.repo).expanduser()
        # `.git` is a dir in a normal checkout, a file in a linked worktree.
        if not (repo / ".git").exists():
            print(f"error: {repo} is not a git repository", file=sys.stderr)
            return 2
        work_root = args.work_root or tempfile.mkdtemp(prefix="maistro-rsi-")
        targets = [t.strip() for t in args.targets.split(",") if t.strip()] if args.targets else []
        config = LocalRsiConfig(
            repo_path=str(repo),
            test_command=args.test_cmd,
            work_root=work_root,
            max_cycles=args.cycles,
            # Only override the config's own default objective when one is given.
            **({"objective": args.objective} if args.objective else {}),
            targets=targets,
            model=args.model,
            agent_turns_per_cycle=args.agent_turns,
            isolation=args.isolation,
            sandbox_image=args.image,
            use_fitness=args.fitness,
            coverage_source=args.coverage_source,
            coverage_pytest_args=args.coverage_pytest_args,
            competitors=parse_competitors(args.competitors),
            scout=args.scout,
            scout_model=args.scout_model,
            export_patches=args.export_patches,
        )
        print(
            f"RSI local loop -> clone of {repo} in {work_root} ({args.cycles} cycles, model={args.model or 'env default'})"
        )
        result = LocalRsiLoop(config).run()
        print("\n" + result.summary())
        return 0

    if args.command == "harvest":
        return _harvest(args)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
