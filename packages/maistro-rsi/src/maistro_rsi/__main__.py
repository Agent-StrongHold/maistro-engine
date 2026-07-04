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
        "--genome-db",
        default=None,
        help="PopulationStore path — activates UNIFIED LIVE EVOLUTION: the genome "
        "population IS the tournament roster, each cycle's real composites fold "
        "back into the genomes (EMA), same-objective variants fight Elo battles, "
        "and cull/breed/hyper-mutation run between cycles. Work is kept "
        "(promoted/exported) exactly as in a plain run; the population persists, "
        "so every run continues the lineage. No separate training evals exist.",
    )
    run.add_argument(
        "--genome-models",
        default="",
        help="CSV of model aliases to seed the genome population across in live "
        "mode (one seed per model — evolution learns per-model differences and "
        "the bench/reliability machinery makes the full roster safe). "
        "Empty ⇒ seed on --model only.",
    )
    run.add_argument(
        "--evolve-goal",
        default="",
        help="Operator goal for the hyper-mutator's meta-prompts in live mode.",
    )
    run.add_argument(
        "--roster-size",
        type=int,
        default=4,
        help="Genomes fielded per cycle in live mode (unscored children get "
        "priority so verification-by-work never starves). Default: 4.",
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
        "--report-every",
        type=int,
        default=0,
        help="Emit a progress report + refreshed patch export every N cycles "
        "(0 = only a final report). The baseline keeps ratcheting — a checkpoint "
        "is an observation point, not a reset.",
    )
    run.add_argument(
        "--report-dir",
        default=None,
        help="Where to write checkpoint reports (checkpoint-*.md/.json) and the "
        "rolling export/. Point this OUTSIDE the edited repo (e.g. a host-mounted "
        "dir) to get reports out of an isolated run.",
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
        "--repo-dir",
        default=None,
        help="Existing checkout to build the PR branches in (local runs).",
    )
    harvest.add_argument(
        "--clone-url",
        default=None,
        help="Clone this repo URL fresh (LF, no host dependency) instead of --repo-dir. "
        "This is the cloud path: a trusted runner clones, applies, and pushes with GH_TOKEN. "
        "Auth for push/PR comes from GH_TOKEN via `gh auth setup-git`.",
    )
    harvest.add_argument(
        "--base",
        default=None,
        help="Branch to base the PR branches on (default: current branch, or the "
        "cloned branch when --clone-url is used).",
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
    harvest.add_argument(
        "--skip-doc-regressions",
        action="store_true",
        help="Drop any promotion that only made an existing docstring vaguer (older runs "
        "predate the no_doc_regression fitness veto), so a harvest keeps the genuinely-new "
        "docstrings but not the specificity regressions.",
    )

    evolve = sub.add_parser(
        "evolve",
        help="Evolve the fixer genome population against a target via the code_rsi benchmark.",
    )
    evolve.add_argument("--repo", required=True, help="Repo to improve (cloned, not touched).")
    evolve.add_argument("--test-cmd", required=True, help="Health test command (exit 0 = healthy).")
    evolve.add_argument("--target", required=True, help="File the genomes compete to improve.")
    evolve.add_argument("--cycles", type=int, default=1, help="Evolution cycles (default: 1).")
    evolve.add_argument("--population", type=int, default=4, help="Population size (default: 4).")
    evolve.add_argument(
        "--models",
        default=None,
        help="Comma-separated gateway aliases to seed genomes with (e.g. "
        "'devstral-medium,codestral,mistral-medium'). Required for a live run — "
        "evolve's own model names are not routable.",
    )
    evolve.add_argument("--coverage-source", default=".")
    evolve.add_argument("--coverage-pytest-args", default="")
    evolve.add_argument("--agent-turns", type=int, default=6)
    evolve.add_argument("--isolation", choices=("local", "container"), default="local")
    evolve.add_argument(
        "--db", default=None, help="PopulationStore path (persists lineage; default: in-memory)."
    )
    evolve.add_argument("--work-root", default=None)
    evolve.add_argument(
        "--goal",
        default="",
        help="Operator goal threaded into the hyper-mutator's meta-prompt "
        "(guides what the fixer population evolves toward).",
    )
    evolve.add_argument(
        "--mutator-model",
        default=None,
        help="Gateway alias for the hyper-mutator's meta-prompts (default: the "
        "first --models entry). Without a reachable gateway the hyper-mutator "
        "simply proposes nothing.",
    )
    return parser


def _evolve(args: argparse.Namespace) -> int:
    import asyncio
    import tempfile

    from maistro_evolve.cycle import EvolutionConfig
    from maistro_evolve.harness import EvalHarness
    from maistro_rsi.code_fixer import LiveCodeFixer
    from maistro_rsi.evolve_bridge import (
        make_code_rsi_runner,
        open_population,
        run_evolution,
        seed_population,
    )
    from maistro_rsi.local_loop import _git

    repo = Path(args.repo).expanduser()
    if not (repo / ".git").exists():
        print(f"error: {repo} is not a git repository", file=sys.stderr)
        return 2
    work_root = Path(args.work_root or tempfile.mkdtemp(prefix="maistro-rsi-evo-"))
    work_root.mkdir(parents=True, exist_ok=True)
    baseline = work_root / "baseline"
    _git(work_root, "clone", "--quiet", str(repo.resolve()), "baseline")
    _git(baseline, "checkout", "-q", "-B", "rsi-baseline")

    fixer = LiveCodeFixer(
        baseline,
        args.test_cmd,
        coverage_source=args.coverage_source,
        coverage_pytest_args=args.coverage_pytest_args,
        agent_turns=args.agent_turns,
        isolation=args.isolation,
    )
    harness = EvalHarness(use_real_benchmarks=False)
    harness.register_benchmark("code_rsi", make_code_rsi_runner(fixer.fix_and_score, args.target))
    store = open_population(args.db)
    models = [m.strip() for m in args.models.split(",") if m.strip()] if args.models else None
    seed_population(store, args.population, models=models)
    cfg = EvolutionConfig(
        target_benchmarks=["code_rsi"],
        population_size=args.population,
        eval_batch_size=args.population,
        tournament_size=2,
        goal=args.goal,
        # Keep breeding/mutation on the routable roster — otherwise a mutated
        # model gene (e.g. gemini-2.5-flash from the generic registry) yields
        # guaranteed-0 evals and spreads through the lineage.
        allowed_models=models or [],
    )

    # The hyper-mutator's meta-LLM: a plain async text->text callable over the
    # gateway. Unconfigured gateway ⇒ stub text ⇒ proposals parse to nothing —
    # evolution still runs, just without guided mutation.
    llm_call = None
    mutator_model = args.mutator_model or (models[0] if models else None)
    if mutator_model:
        from maistro_bootstrap.builders.responses_callable import ResponsesAPICallable

        callable_ = ResponsesAPICallable(model=mutator_model, timeout=300.0)

        async def llm_call(prompt: str) -> str:
            result = await asyncio.to_thread(callable_, [{"role": "user", "content": prompt}])
            content = result.get("content", "") if isinstance(result, dict) else result
            return content if isinstance(content, str) else str(content)

    print(
        f"RSI evolve -> {args.population} genomes x {args.cycles} cycle(s) on {args.target} "
        f"(models={models or 'evolve defaults (not routable!)'}, "
        f"hyper-mutator={mutator_model or 'off'})"
    )
    asyncio.run(run_evolution(store, harness, args.cycles, config=cfg, llm_call=llm_call))

    genomes = store.list_all()
    print(f"\nEvolution complete: {len(genomes)} genomes")
    for g in sorted(genomes, key=lambda x: x.fitness_score or -1.0, reverse=True)[:12]:
        nodes = g.topology.nodes
        entry = next((n for n in nodes if n.id == g.topology.entry_node), nodes[0])
        print(
            f"  {g.name} gen{g.generation} model={entry.model} "
            f"code_rsi={g.eval_scores.get('code_rsi')} fitness={g.fitness_score}"
        )
    champ = store.get_champion()
    if champ is not None:
        print(f"champion: {champ.name} (fitness={champ.fitness_score})")
    return 0


def _harvest(args: argparse.Namespace) -> int:  # noqa: C901  clone/repo setup + am/skip/PR loop
    import subprocess
    import tempfile
    from datetime import UTC, datetime

    from maistro_evolve.doc_regression import doc_regressions
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
    if not (args.repo_dir or args.clone_url):
        print("error: pass --repo-dir (local) or --clone-url (cloud)", file=sys.stderr)
        return 2
    session = args.session or datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    base = args.base
    if args.clone_url:
        # Cloud path: wire GH_TOKEN into git FIRST (so a private clone + the push
        # both authenticate), then clone fresh with an LF working tree (no CRLF
        # host artifacts). The credential lives only in this trusted step.
        if args.push:
            subprocess.run(["gh", "auth", "setup-git"], check=True)
        repo = tempfile.mkdtemp(prefix="rsi-harvest-")
        clone_base = base or "main"
        subprocess.run(
            [
                "git",
                "-c",
                "core.autocrlf=false",
                "clone",
                "--single-branch",
                "--branch",
                clone_base,
                args.clone_url,
                repo,
            ],
            check=True,
        )
        base = clone_base
    else:
        repo = str(Path(args.repo_dir).resolve())

    # Identity flags so `git am` can commit in a clone with no configured user
    # (the RSI commits are bot commits); --3way lets am fall back to a blob-level
    # 3-way merge when line-ending/context differs from the patch's base.
    ident = ["-c", "user.email=rsi@maistro.local", "-c", "user.name=maistro-rsi"]

    def git(*a: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *ident, "-C", repo, *a], check=check, capture_output=True, text=True
        )

    # base is set above for --clone-url; for --repo-dir default to its current branch.
    base = base or git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    def _regresses_docs(rel: str) -> bool:
        # Compare the file just committed (HEAD) against its parent (HEAD~1).
        if not rel.endswith(".py"):
            return False
        before = git("show", f"HEAD~1:{rel}", check=False)
        after = git("show", f"HEAD:{rel}", check=False)
        if before.returncode != 0 or after.returncode != 0:
            return False
        return bool(doc_regressions(before.stdout, after.stdout))

    opened = 0
    skipped = 0
    unappliable = 0
    for file, group in groups.items():
        branch = branch_slug(file, session)
        git("checkout", "-B", branch, base)
        kept_patches = []
        for patch in group:
            # A patch from an older run may no longer apply once the base has
            # moved past it (even with --3way). Skip it and keep harvesting —
            # one stale patch must not sink the rest of the run's promotions.
            am = git("am", "--3way", str((export / patch.patch_file).resolve()), check=False)
            if am.returncode != 0:
                git("am", "--abort", check=False)
                unappliable += 1
                continue
            if args.skip_doc_regressions and _regresses_docs(file):
                git("reset", "--hard", "HEAD~1")  # drop the doc-specificity regression
                skipped += 1
                continue
            kept_patches.append(patch)
        if not kept_patches:
            print(f"[skipped] {branch}  <- {file}  (0 of {len(group)} promotion(s) kept)")
            continue
        action = "pushed + PR" if args.push else "built (dry-run)"
        print(f"[{action}] {branch}  <- {file}  ({len(kept_patches)} commit(s))")
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
                    pr_title(file, kept_patches),
                    "--body",
                    pr_body(file, kept_patches),
                ],
                cwd=repo,
                check=True,
            )
            opened += 1
    git("checkout", base, check=False)
    tail = f", {skipped} doc-regression(s) dropped" if skipped else ""
    if unappliable:
        tail += f", {unappliable} stale patch(es) no longer apply"
    print(f"\nharvest: {len(groups)} file group(s), {opened} PR(s) opened{tail}")
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
        competitors = parse_competitors(args.competitors)
        if args.genome_db:
            print(
                f"live evolution: population at {args.genome_db} IS the roster — "
                "work is kept AND scores the genomes; lineage continues across runs"
            )
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
            competitors=competitors,
            scout=args.scout,
            scout_model=args.scout_model,
            export_patches=args.export_patches,
            report_every=args.report_every,
            report_dir=args.report_dir,
            genome_db=args.genome_db,
            genome_models=[m.strip() for m in args.genome_models.split(",") if m.strip()],
            evolve_goal=args.evolve_goal,
            roster_size=args.roster_size,
        )
        print(
            f"RSI local loop -> clone of {repo} in {work_root} ({args.cycles} cycles, model={args.model or 'env default'})"
        )
        result = LocalRsiLoop(config).run()
        print("\n" + result.summary())
        return 0

    if args.command == "harvest":
        return _harvest(args)

    if args.command == "evolve":
        return _evolve(args)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
