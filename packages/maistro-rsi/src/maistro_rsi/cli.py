"""Operational CLI for resumable autonomous RSI campaigns."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

from maistro_rsi.campaign import (
    DEFAULT_PROTECTED_PATHS,
    AutonomousCampaign,
    CampaignConfig,
    CampaignState,
    CampaignStore,
    WorkspaceFactory,
    isolated_workspace_factory,
    worktree_workspace_factory,
)
from maistro_rsi.patch_agent import EvolvingToolLoopPatchProvider


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    state_root = Path(args.state_dir).expanduser()
    try:
        if args.command == "start":
            state = start_campaign(
                state_root=state_root,
                campaign_id=args.campaign_id,
                repo_url=args.repo_url,
                objective=args.objective,
                test_command=args.test_command,
                benchmark_command=args.benchmark_command,
                base_ref=args.base_ref,
                max_iterations=args.max_iterations,
                provider_failure_limit=args.provider_failure_limit,
                provider_retry_delay_seconds=args.provider_retry_delay_seconds,
                model=args.model,
                provider=args.provider,
                ollama_url=args.ollama_url,
                sandbox_image=args.sandbox_image,
                protected_paths=args.protected_path,
                worktree=args.worktree,
            )
        elif args.command == "resume":
            state = resume_campaign(state_root=state_root, campaign_id=args.campaign_id)
        elif args.command == "stop":
            state = stop_campaign(state_root=state_root, campaign_id=args.campaign_id)
        else:
            state = campaign_status(state_root=state_root, campaign_id=args.campaign_id)
    except Exception as exc:
        print(f"maistro-rsi: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(asdict(state), indent=2, sort_keys=True))


def start_campaign(
    *,
    state_root: Path,
    campaign_id: str | None,
    repo_url: str,
    objective: str,
    test_command: str,
    benchmark_command: str | None,
    base_ref: str,
    max_iterations: int,
    provider_failure_limit: int,
    provider_retry_delay_seconds: float,
    model: str | None,
    provider: str,
    ollama_url: str,
    sandbox_image: str | None,
    protected_paths: list[str] | None,
    worktree: bool,
) -> CampaignState:
    resolved_id = campaign_id or f"rsi-{uuid.uuid4().hex[:10]}"
    store = CampaignStore.for_campaign(state_root, resolved_id)
    config = CampaignConfig(
        campaign_id=resolved_id,
        repo_url=repo_url,
        objective=objective,
        test_command=test_command,
        benchmark_command=benchmark_command,
        base_ref=base_ref,
        max_iterations=max_iterations,
        provider_failure_limit=provider_failure_limit,
        provider_retry_delay_seconds=provider_retry_delay_seconds,
        provider_model=model,
        sandbox_image=sandbox_image,
        protected_paths=tuple(protected_paths or DEFAULT_PROTECTED_PATHS),
    )
    campaign = _campaign(store, model=model, provider=provider, ollama_url=ollama_url, worktree=worktree)
    asyncio.run(campaign.initialize(config))
    return asyncio.run(campaign.run())


def resume_campaign(*, state_root: Path, campaign_id: str) -> CampaignState:
    store = CampaignStore.for_campaign(state_root, campaign_id)
    config = store.load_config()
    # Resume always uses the same factory as the original start — inferred from
    # the campaign state directory (worktree mode stores no image, VM mode does).
    worktree = config.sandbox_image is None and (store.root / "worktree.mode").is_file()
    return asyncio.run(
        _campaign(store, model=config.provider_model, provider="codex", ollama_url="", worktree=worktree).resume()
    )


def campaign_status(*, state_root: Path, campaign_id: str) -> CampaignState:
    return CampaignStore.for_campaign(state_root, campaign_id).load_state()


def stop_campaign(*, state_root: Path, campaign_id: str) -> CampaignState:
    return CampaignStore.for_campaign(state_root, campaign_id).request_stop()


def _campaign(
    store: CampaignStore,
    *,
    model: str | None,
    provider: str,
    ollama_url: str,
    worktree: bool,
) -> AutonomousCampaign:
    llm = _make_llm(provider=provider, model=model, ollama_url=ollama_url)
    factory: WorkspaceFactory
    require_vm = True
    if worktree:
        factory = worktree_workspace_factory
        require_vm = False
        # Leave a breadcrumb so resume knows we were in worktree mode.
        (store.root / "worktree.mode").touch()
    else:
        factory = isolated_workspace_factory
    return AutonomousCampaign(
        store=store,
        provider=EvolvingToolLoopPatchProvider(
            llm,
            state_path=store.root / "evolved-strategy.txt",
        ),
        workspace_factory=factory,
        require_vm_isolation=require_vm,
    )


def _make_llm(*, provider: str, model: str | None, ollama_url: str) -> object:
    if provider == "ollama":
        from maistro_evolve.providers.ollama import OllamaProvider

        resolved_model = model or os.environ.get("MAISTRO_RSI_MODEL", "")
        if not resolved_model:
            raise ValueError(
                "Ollama provider requires --model or MAISTRO_RSI_MODEL env var. "
                "Example: --model qwen2.5-coder:7b"
            )
        return OllamaProvider(model=resolved_model, base_url=ollama_url)
    # Default: CodexCLI
    from maistro_evolve.providers.codex_cli import CodexCliProvider

    return CodexCliProvider(model=model)


def _parser() -> argparse.ArgumentParser:
    default_state = str(default_state_root())
    parser = argparse.ArgumentParser(prog="maistro-rsi")
    parser.add_argument("--state-dir", default=default_state)
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("start")
    start.add_argument("--campaign-id")
    start.add_argument("--repo-url", required=True)
    start.add_argument("--objective", required=True)
    start.add_argument("--test-command", required=True)
    start.add_argument("--benchmark-command")
    start.add_argument("--base-ref", default="develop")
    start.add_argument("--max-iterations", type=int, default=10)
    start.add_argument("--provider-failure-limit", type=int, default=3)
    start.add_argument("--provider-retry-delay-seconds", type=float, default=30.0)
    start.add_argument("--model", help="Model name passed to the provider")
    start.add_argument(
        "--provider",
        choices=["codex", "ollama"],
        default="codex",
        help="LLM provider. Use 'ollama' for a local Ollama instance.",
    )
    start.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434)",
    )
    start.add_argument("--sandbox-image")
    start.add_argument("--protected-path", action="append")
    start.add_argument(
        "--worktree",
        action="store_true",
        default=False,
        help=(
            "Trusted-development mode: use a local git worktree instead of a VM "
            "sandbox. Fast iteration only — never use for untrusted model-generated code."
        ),
    )

    for name in ("resume", "status", "stop"):
        command = commands.add_parser(name)
        command.add_argument("campaign_id")

    return parser


def default_state_root() -> Path:
    configured = os.environ.get("MAISTRO_RSI_STATE_DIR")
    if configured:
        return Path(configured).expanduser()
    maistro_root = os.environ.get("MAISTRO_STATE_DIR")
    if maistro_root:
        return Path(maistro_root).expanduser() / "rsi"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Maistro/rsi"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Maistro/rsi"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "maistro/rsi"


if __name__ == "__main__":
    main()
