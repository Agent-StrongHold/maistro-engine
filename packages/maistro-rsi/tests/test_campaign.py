"""Contracts for the real resumable autonomous campaign path."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from maistro.sandbox.protocol import ExecResult
from maistro_rsi.campaign import (
    AutonomousCampaign,
    CampaignConfig,
    CampaignStatus,
    CampaignStore,
    CandidateProposal,
    CandidateRequest,
    ProposalWorkspace,
)

BASE_COMMIT = "b" * 40
FIX_PATCH = "diff --git a/fix.py b/fix.py\n"
BAD_PATCH = "diff --git a/bad.py b/bad.py\n"


class FakeWorkspace:
    def __init__(self, patch: str | None) -> None:
        self.patch = patch or ""
        self.closed = False
        self.files: dict[str, str] = {}
        self.generated_patch = ""

    @property
    def base_commit(self) -> str:
        return BASE_COMMIT

    @property
    def isolation_tier(self) -> str:
        return "vm"

    @property
    def backend_name(self) -> str:
        return "fake-vm"

    @property
    def git_version(self) -> str:
        return "git version 2.54.0"

    def read_file(self, path: str) -> str:
        return self.files[path]

    def write_file(self, path: str, content: str) -> None:
        self.files[path] = content
        self.generated_patch = f"diff --git a/{path} b/{path}\n"

    def delete_file(self, path: str) -> None:
        self.files.pop(path, None)
        self.generated_patch = f"diff --git a/{path} b/{path}\n"

    def run_command_result(self, cmd: str, *, timeout: int = 30) -> ExecResult:
        if cmd == "pytest -q":
            passed = FIX_PATCH in self.patch
            return ExecResult(int(not passed), "passed" if passed else "failed", "", 1)
        if cmd == "python benchmark.py":
            score = 0.9 if FIX_PATCH in self.patch else 0.4
            return ExecResult(0, f'{{"fidelity":"real","score":{score}}}\n', "", 1)
        raise AssertionError(f"unexpected command: {cmd}")

    def search(self, pattern: str, *, glob: str = "**/*.py") -> list[str]:
        return []

    def list_files(self, *, glob: str = "**/*", limit: int = 2000) -> list[str]:
        return list(self.files)[:limit]

    def diff(self) -> str:
        return self.generated_patch or self.patch

    def close(self) -> None:
        self.closed = True


class RecordingWorkspaceFactory:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.workspaces: list[FakeWorkspace] = []

    def __call__(self, **kwargs: object) -> FakeWorkspace:
        self.calls.append(kwargs)
        workspace = FakeWorkspace(
            kwargs.get("patch") if isinstance(kwargs.get("patch"), str) else None
        )
        self.workspaces.append(workspace)
        return workspace


class FailingEvaluationFactory(RecordingWorkspaceFactory):
    def __call__(self, **kwargs: object) -> FakeWorkspace:
        if kwargs.get("patch") == FIX_PATCH:
            raise RuntimeError("evaluation backend unavailable")
        return super().__call__(**kwargs)


class NonVmWorkspace(FakeWorkspace):
    @property
    def isolation_tier(self) -> str:
        return "container"


class NonVmFactory:
    def __call__(self, **kwargs: object) -> NonVmWorkspace:
        return NonVmWorkspace(None)


@dataclass
class FixedProvider:
    patch: str
    calls: int = 0

    async def propose(
        self, workspace: ProposalWorkspace, request: CandidateRequest
    ) -> CandidateProposal:
        self.calls += 1
        assert not hasattr(workspace, "run_command_result")
        path = self.patch.split(" a/", 1)[1].split(" b/", 1)[0]
        workspace.write_file(path, "candidate")
        return CandidateProposal("candidate")


class FailingProvider:
    async def propose(
        self, workspace: ProposalWorkspace, request: CandidateRequest
    ) -> CandidateProposal:
        raise RuntimeError("provider offline")


def _config(campaign_id: str, **overrides: object) -> CampaignConfig:
    values: dict[str, object] = {
        "campaign_id": campaign_id,
        "repo_url": "https://github.com/acme/widget",
        "objective": "repair the failing test",
        "test_command": "pytest -q",
        "base_ref": "develop",
        "max_iterations": 1,
        "provider_retry_delay_seconds": 0,
    }
    values.update(overrides)
    return CampaignConfig(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_campaign_pins_develop_and_uses_fresh_offline_workspaces(tmp_path: Path) -> None:
    store = CampaignStore.for_campaign(tmp_path, "fresh")
    factory = RecordingWorkspaceFactory()
    campaign = AutonomousCampaign(
        store=store,
        provider=FixedProvider(FIX_PATCH),
        workspace_factory=factory,
    )

    await campaign.initialize(_config("fresh"))
    state = await campaign.run()

    assert state.status is CampaignStatus.COMPLETED
    assert state.base_commit == BASE_COMMIT
    assert state.accepted_candidates == 1
    assert len(factory.workspaces) == 4
    assert len({id(workspace) for workspace in factory.workspaces}) == 4
    assert factory.calls[0]["base_ref"] == "develop"
    assert all(call.get("base_commit") == BASE_COMMIT for call in factory.calls[1:])
    assert all(workspace.closed for workspace in factory.workspaces)
    assert store.load_accepted_patch() == FIX_PATCH


@pytest.mark.asyncio
async def test_campaign_initialization_rejects_non_vm_workspace(tmp_path: Path) -> None:
    store = CampaignStore.for_campaign(tmp_path, "non-vm")
    campaign = AutonomousCampaign(
        store=store,
        provider=FixedProvider(FIX_PATCH),
        workspace_factory=NonVmFactory(),
    )

    with pytest.raises(RuntimeError, match="VM-grade"):
        await campaign.initialize(_config("non-vm"))

    assert store.load_state().status is CampaignStatus.FAILED


@pytest.mark.asyncio
async def test_real_benchmark_score_can_accept_candidate_with_passing_tests(tmp_path: Path) -> None:
    store = CampaignStore.for_campaign(tmp_path, "benchmark")
    factory = RecordingWorkspaceFactory()
    campaign = AutonomousCampaign(
        store=store,
        provider=FixedProvider(FIX_PATCH),
        workspace_factory=factory,
    )
    await campaign.initialize(
        _config(
            "benchmark",
            benchmark_command="python benchmark.py",
        )
    )

    state = await campaign.run()

    assert state.accepted_candidates == 1
    records = store.ledger.records()
    benchmark_scores = [
        record["quality_score"]
        for record in records
        if str(record.get("phase", "")).endswith("-benchmark")
    ]
    assert benchmark_scores == [0.4, 0.9]


@pytest.mark.asyncio
async def test_rejected_candidate_never_replaces_incumbent(tmp_path: Path) -> None:
    store = CampaignStore.for_campaign(tmp_path, "rejected")
    factory = RecordingWorkspaceFactory()
    campaign = AutonomousCampaign(
        store=store,
        provider=FixedProvider(BAD_PATCH),
        workspace_factory=factory,
    )
    await campaign.initialize(_config("rejected"))

    state = await campaign.run()

    assert state.accepted_candidates == 0
    assert store.load_accepted_patch() == ""
    event = next(
        event
        for event in (
            __import__("json").loads(line)
            for line in (store.root / "events.jsonl").read_text(encoding="utf-8").splitlines()
        )
        if event["type"] == "trial"
    )
    assert event["promotion_eligible"] is False


@pytest.mark.asyncio
async def test_candidate_cannot_replace_protected_benchmark_or_tests(tmp_path: Path) -> None:
    protected_patch = "diff --git a/tests/test_truth.py b/tests/test_truth.py\n"
    store = CampaignStore.for_campaign(tmp_path, "protected")
    factory = RecordingWorkspaceFactory()
    campaign = AutonomousCampaign(
        store=store,
        provider=FixedProvider(protected_patch),
        workspace_factory=factory,
    )
    await campaign.initialize(_config("protected"))

    state = await campaign.run()

    assert state.accepted_candidates == 0
    assert store.load_accepted_patch() == ""
    assert len(factory.workspaces) == 3


@pytest.mark.asyncio
async def test_provider_outage_is_durable_and_resumable(tmp_path: Path) -> None:
    store = CampaignStore.for_campaign(tmp_path, "resume")
    first_factory = RecordingWorkspaceFactory()
    failed = AutonomousCampaign(
        store=store,
        provider=FailingProvider(),
        workspace_factory=first_factory,
    )
    await failed.initialize(_config("resume", provider_failure_limit=1))

    stopped = await failed.run()

    assert stopped.status is CampaignStatus.PROVIDER_UNAVAILABLE
    assert stopped.iteration == 0
    assert "provider offline" in (stopped.last_error or "")

    resumed_factory = RecordingWorkspaceFactory()
    resumed = AutonomousCampaign(
        store=store,
        provider=FixedProvider(FIX_PATCH),
        workspace_factory=resumed_factory,
    )
    completed = await resumed.resume()

    assert completed.status is CampaignStatus.COMPLETED
    assert completed.iteration == 1
    assert all(call["base_commit"] == BASE_COMMIT for call in resumed_factory.calls)


@pytest.mark.asyncio
async def test_durable_stop_and_resume(tmp_path: Path) -> None:
    store = CampaignStore.for_campaign(tmp_path, "stop")
    factory = RecordingWorkspaceFactory()
    campaign = AutonomousCampaign(
        store=store,
        provider=FixedProvider(FIX_PATCH),
        workspace_factory=factory,
    )
    await campaign.initialize(_config("stop"))
    store.request_stop()

    stopped = await campaign.run()

    assert stopped.status is CampaignStatus.STOPPED
    assert stopped.iteration == 0

    completed = await campaign.resume()

    assert completed.status is CampaignStatus.COMPLETED
    assert completed.iteration == 1


@pytest.mark.asyncio
async def test_infrastructure_failure_is_durable_and_resumable(tmp_path: Path) -> None:
    store = CampaignStore.for_campaign(tmp_path, "infra")
    failed = AutonomousCampaign(
        store=store,
        provider=FixedProvider(FIX_PATCH),
        workspace_factory=FailingEvaluationFactory(),
    )
    await failed.initialize(_config("infra"))

    stopped = await failed.run()

    assert stopped.status is CampaignStatus.FAILED
    assert "evaluation backend unavailable" in (stopped.last_error or "")

    resumed = AutonomousCampaign(
        store=store,
        provider=FixedProvider(FIX_PATCH),
        workspace_factory=RecordingWorkspaceFactory(),
    )
    completed = await resumed.resume()

    assert completed.status is CampaignStatus.COMPLETED
    assert completed.accepted_candidates == 1
