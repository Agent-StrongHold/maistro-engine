"""Durable, VM-isolated autonomous RSI campaign orchestration."""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import warnings
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from maistro.sandbox.protocol import ExecResult
from maistro_rsi.experiment import (
    CommandMeasurement,
    ExperimentDecision,
    ExperimentLedger,
    decide_candidate,
    measure_command,
)

if TYPE_CHECKING:
    from maistro.security.warden.detector import Warden
    from maistro_rsi.quarantine import AdversarialReview

_CAMPAIGN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,127}$")
_COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{40,64}$")
_MAX_PATCH_BYTES = 32 * 1024 * 1024
DEFAULT_PROTECTED_PATHS = (
    ".github",
    "benchmarks",
    "conftest.py",
    "tests",
)


class CampaignStatus(StrEnum):
    """Durable lifecycle states for an autonomous campaign."""

    INITIALIZING = "initializing"
    RUNNING = "running"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class CampaignConfig:
    """Immutable campaign inputs."""

    campaign_id: str
    repo_url: str
    objective: str
    test_command: str
    benchmark_command: str | None = None
    base_ref: str = "develop"
    max_iterations: int = 10
    command_timeout_seconds: int = 900
    provider_failure_limit: int = 3
    provider_retry_delay_seconds: float = 30.0
    minimum_speedup: float | None = None
    provider_model: str | None = None
    sandbox_image: str | None = None
    protected_paths: tuple[str, ...] = field(default_factory=lambda: DEFAULT_PROTECTED_PATHS)

    def validate(self) -> None:
        from maistro.builders.isolated_workspace import validate_git_ref, validate_repo_url
        validate_repo_url(self.repo_url)
        validate_git_ref(self.base_ref)
        if not _CAMPAIGN_ID.fullmatch(self.campaign_id):
            raise ValueError(f"Invalid campaign ID: {self.campaign_id!r}")
        if not self.objective.strip():
            raise ValueError("Campaign objective must not be empty")
        if not self.test_command.strip():
            raise ValueError("Campaign test command must not be empty")
        if self.max_iterations < 1:
            raise ValueError("Campaign max_iterations must be positive")
        if self.command_timeout_seconds < 1:
            raise ValueError("Campaign command timeout must be positive")
        if self.provider_failure_limit < 1:
            raise ValueError("Campaign provider failure limit must be positive")
        if self.provider_retry_delay_seconds < 0:
            raise ValueError("Campaign provider retry delay must not be negative")
        if self.minimum_speedup is not None and not 0 < self.minimum_speedup < 1:
            raise ValueError("Campaign minimum_speedup must be between zero and one")
        if any(not path or path.startswith(("/", "\\")) or ".." in Path(path).parts for path in self.protected_paths):
            raise ValueError("Campaign protected paths must be non-empty relative paths")


@dataclass(frozen=True)
class CampaignState:
    """Mutable state persisted atomically after each meaningful transition."""

    campaign_id: str
    status: CampaignStatus
    base_commit: str | None
    iteration: int
    accepted_candidates: int
    consecutive_provider_failures: int
    last_error: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CandidateRequest:
    """Information supplied to a controller-side candidate provider."""

    campaign_id: str
    iteration: int
    objective: str
    test_command: str
    benchmark_command: str | None
    baseline_test: CommandMeasurement
    baseline_benchmark: CommandMeasurement | None
    prior_feedback: str | None


@dataclass(frozen=True)
class CandidateProposal:
    """Controller-side provider metadata; Maistro itself exports the patch."""

    summary: str
    provider_transcript: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class TrialResult:
    """One persisted baseline/candidate comparison."""

    iteration: int
    accepted: bool
    reason: str
    candidate_patch_file: str | None
    baseline_test: CommandMeasurement
    candidate_test: CommandMeasurement | None
    baseline_benchmark: CommandMeasurement | None
    candidate_benchmark: CommandMeasurement | None


class CampaignWorkspace(Protocol):
    """Only the offline workspace capabilities used by a campaign."""

    @property
    def base_commit(self) -> str: ...

    @property
    def isolation_tier(self) -> str: ...

    @property
    def backend_name(self) -> str: ...

    @property
    def git_version(self) -> str: ...

    def read_file(self, path: str) -> str: ...

    def write_file(self, path: str, content: str) -> None: ...

    def delete_file(self, path: str) -> None: ...

    def run_command_result(self, cmd: str, *, timeout: int = 30) -> ExecResult: ...

    def search(self, pattern: str, *, glob: str = "**/*.py") -> list[str]: ...

    def list_files(self, *, glob: str = "**/*", limit: int = 2000) -> list[str]: ...

    def diff(self) -> str: ...

    def close(self) -> None: ...


class ProposalWorkspace(Protocol):
    """Non-executing view exposed to a controller-side candidate provider."""

    def read_file(self, path: str) -> str: ...

    def write_file(self, path: str, content: str) -> None: ...

    def delete_file(self, path: str) -> None: ...

    def search(self, pattern: str, *, glob: str = "**/*.py") -> list[str]: ...

    def list_files(self, *, glob: str = "**/*", limit: int = 2000) -> list[str]: ...


class CandidateProvider(Protocol):
    """Controller-side agent that may operate only through an offline workspace."""

    async def propose(
        self, workspace: ProposalWorkspace, request: CandidateRequest
    ) -> CandidateProposal: ...


WorkspaceFactory = Callable[..., CampaignWorkspace]


def isolated_workspace_factory(
    *,
    repo_url: str,
    patch: str | None = None,
    base_commit: str | None = None,
    base_ref: str | None = None,
    image_ref: str | None = None,
) -> CampaignWorkspace:
    """Create the production VM-grade offline Builders workspace."""
    from maistro.builders.isolated_workspace import IsolatedBuilderSandbox
    return cast(
        CampaignWorkspace,
        IsolatedBuilderSandbox.create(
            repo_url,
            patch=patch,
            base_commit=base_commit,
            base_ref=base_ref,
            image_ref=image_ref,
        ),
    )


def worktree_workspace_factory(
    *,
    repo_url: str,  # noqa: ARG001 — ignored; worktree uses the local checkout
    patch: str | None = None,
    base_commit: str | None = None,
    base_ref: str | None = None,
    image_ref: str | None = None,  # noqa: ARG001 — no image in worktree mode
) -> CampaignWorkspace:
    """Create a trusted-development workspace backed by a local git worktree.

    WARNING: runs host subprocesses with the caller's permissions.
    Only for trusted local development. Use isolated_workspace_factory for
    untrusted model-generated code.
    """
    from maistro_rsi.workspaces.worktree import WorktreeCampaignWorkspace

    return cast(
        CampaignWorkspace,
        WorktreeCampaignWorkspace.create(
            patch=patch,
            base_commit=base_commit,
            base_ref=base_ref,
        ),
    )


class CampaignStore:
    """Atomic campaign state plus append-only evidence and immutable patches."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    @classmethod
    def for_campaign(cls, state_root: Path, campaign_id: str) -> CampaignStore:
        if not _CAMPAIGN_ID.fullmatch(campaign_id):
            raise ValueError(f"Invalid campaign ID: {campaign_id!r}")
        root = state_root.resolve()
        target = (root / campaign_id).resolve()
        target.relative_to(root)
        return cls(target)

    def create(self, config: CampaignConfig) -> CampaignState:
        config.validate()
        if self.root.exists():
            raise FileExistsError(f"Campaign already exists: {config.campaign_id}")
        self.root.mkdir(parents=True)
        now = _now()
        state = CampaignState(
            campaign_id=config.campaign_id,
            status=CampaignStatus.INITIALIZING,
            base_commit=None,
            iteration=0,
            accepted_candidates=0,
            consecutive_provider_failures=0,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        self._atomic_json(self.root / "config.json", asdict(config))
        self.save_state(state)
        self._atomic_write(self.root / "accepted.patch", b"")
        return state

    def load_config(self) -> CampaignConfig:
        data = cast(dict[str, Any], self._read_json(self.root / "config.json"))
        data["protected_paths"] = tuple(data["protected_paths"])
        return CampaignConfig(**data)

    def load_state(self) -> CampaignState:
        data = cast(dict[str, Any], self._read_json(self.root / "state.json"))
        data["status"] = CampaignStatus(data["status"])
        return CampaignState(**data)

    def save_state(self, state: CampaignState) -> None:
        self._atomic_json(self.root / "state.json", asdict(state))

    def load_accepted_patch(self) -> str:
        return (self.root / "accepted.patch").read_text(encoding="utf-8")

    def save_candidate(self, iteration: int, patch: str, proposal: CandidateProposal) -> str:
        encoded = patch.encode("utf-8")
        if len(encoded) > _MAX_PATCH_BYTES:
            raise ValueError(f"Candidate patch exceeds {_MAX_PATCH_BYTES} bytes")
        relative = f"candidates/{iteration:04d}.patch"
        self._atomic_write(self.root / relative, encoded)
        self._atomic_json(
            self.root / f"candidates/{iteration:04d}.json",
            {
                "iteration": iteration,
                "summary": proposal.summary,
                "provider_transcript": proposal.provider_transcript,
                "recorded_at": _now(),
            },
        )
        return relative

    def accept_candidate(self, patch: str) -> None:
        self._atomic_write(self.root / "accepted.patch", patch.encode("utf-8"))

    def append_event(self, event: dict[str, object]) -> None:
        path = self.root / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def request_stop(self) -> CampaignState:
        self._atomic_write(self.root / "stop.requested", _now().encode("utf-8"))
        state = replace(
            self.load_state(),
            status=CampaignStatus.STOPPED,
            updated_at=_now(),
        )
        self.save_state(state)
        self.append_event({"type": "stop_requested", "recorded_at": _now()})
        return state

    def stop_requested(self) -> bool:
        return (self.root / "stop.requested").is_file()

    def clear_stop(self) -> None:
        (self.root / "stop.requested").unlink(missing_ok=True)

    def last_trial_feedback(self) -> str | None:
        events_path = self.root / "events.jsonl"
        event_reason: str | None = None
        if events_path.is_file():
            for line in reversed(events_path.read_text(encoding="utf-8").splitlines()):
                event = json.loads(line)
                if event.get("type") == "trial":
                    event_reason = str(event.get("reason", ""))
                    break
        candidate_output: str | None = None
        for record in reversed(self.ledger.records()):
            if (
                record.get("type") == "measurement"
                and str(record.get("phase", "")).startswith("candidate-")
            ):
                candidate_output = str(record.get("output", ""))[-4000:]
                break
        if event_reason is None and candidate_output is None:
            return None
        return f"Prior decision: {event_reason or 'unknown'}\nPrior candidate evidence:\n{candidate_output or 'none'}"

    @property
    def ledger(self) -> ExperimentLedger:
        return ExperimentLedger(self.root / "measurements.jsonl")

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError(f"Expected JSON object in {path}")
        return cast(dict[str, object], parsed)

    @staticmethod
    def _atomic_json(path: Path, value: object) -> None:
        CampaignStore._atomic_write(
            path, json.dumps(value, indent=2, sort_keys=True).encode("utf-8")
        )

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)


class AutonomousCampaign:
    """Run resumable candidate generation and evaluation with fresh VM workspaces."""

    def __init__(
        self,
        *,
        store: CampaignStore,
        provider: CandidateProvider,
        workspace_factory: WorkspaceFactory = isolated_workspace_factory,
        require_vm_isolation: bool = True,
        warden: Warden | None = None,
        adversarial_review: AdversarialReview | None = None,
    ) -> None:
        self.store = store
        self.provider = provider
        self.workspace_factory = workspace_factory
        self._require_vm_isolation = require_vm_isolation
        self._warden = warden
        self._adversarial_review = adversarial_review

    async def initialize(self, config: CampaignConfig) -> CampaignState:
        state = self.store.create(config)
        workspace = self.workspace_factory(
            repo_url=config.repo_url,
            patch=None,
            base_commit=None,
            base_ref=config.base_ref,
            image_ref=config.sandbox_image,
        )
        try:
            base_commit = workspace.base_commit
            if not _COMMIT_SHA.fullmatch(base_commit):
                raise RuntimeError("Workspace returned an invalid base commit")
            if workspace.isolation_tier != "vm":
                if self._require_vm_isolation:
                    raise RuntimeError("Autonomous campaigns require VM-grade isolation")
                warnings.warn(
                    f"Campaign {config.campaign_id!r} running with "
                    f"{workspace.isolation_tier!r} isolation — trusted development mode only. "
                    "Switch to isolated_workspace_factory for untrusted model-generated code.",
                    stacklevel=2,
                )
            git_version = workspace.git_version
            sandbox_backend = workspace.backend_name
            isolation_tier = workspace.isolation_tier
        except Exception as exc:
            failed = replace(
                state,
                status=CampaignStatus.FAILED,
                last_error=str(exc),
                updated_at=_now(),
            )
            self.store.save_state(failed)
            raise
        finally:
            workspace.close()
        running = replace(
            state,
            status=CampaignStatus.RUNNING,
            base_commit=base_commit,
            updated_at=_now(),
        )
        self.store.save_state(running)
        self.store.append_event(
            {
                "type": "initialized",
                "base_commit": base_commit,
                "sandbox_backend": sandbox_backend,
                "isolation_tier": isolation_tier,
                "git_version": git_version,
                "recorded_at": _now(),
            }
        )
        return running

    async def run(self) -> CampaignState:
        config = self.store.load_config()
        state = self.store.load_state()
        if state.status is not CampaignStatus.RUNNING:
            return state
        if state.base_commit is None:
            raise RuntimeError("Campaign has no pinned base commit")

        while state.iteration < config.max_iterations:
            if self.store.stop_requested():
                stopped = replace(state, status=CampaignStatus.STOPPED, updated_at=_now())
                self.store.save_state(stopped)
                self.store.append_event({"type": "stopped", "recorded_at": _now()})
                return stopped
            try:
                state = await self._run_trial(config, state)
            except Exception as exc:
                failed = replace(
                    state,
                    status=CampaignStatus.FAILED,
                    last_error=str(exc),
                    updated_at=_now(),
                )
                self.store.save_state(failed)
                self.store.append_event(
                    {"type": "failure", "error": str(exc), "recorded_at": _now()}
                )
                return failed
            if state.status is not CampaignStatus.RUNNING:
                return state
            if state.consecutive_provider_failures:
                await asyncio.sleep(config.provider_retry_delay_seconds)
        completed = replace(state, status=CampaignStatus.COMPLETED, updated_at=_now())
        self.store.save_state(completed)
        self.store.append_event({"type": "completed", "recorded_at": _now()})
        return completed

    async def resume(self) -> CampaignState:
        """Clear a durable stop/failure state and retry from persisted artifacts."""
        state = self.store.load_state()
        if state.status is CampaignStatus.COMPLETED:
            return state
        self.store.clear_stop()
        running = replace(
            state,
            status=CampaignStatus.RUNNING,
            consecutive_provider_failures=0,
            last_error=None,
            updated_at=_now(),
        )
        self.store.save_state(running)
        self.store.append_event({"type": "resumed", "recorded_at": _now()})
        return await self.run()

    async def _run_trial(self, config: CampaignConfig, state: CampaignState) -> CampaignState:
        assert state.base_commit is not None
        iteration = state.iteration + 1
        incumbent_patch = self.store.load_accepted_patch()
        baseline_test, baseline_benchmark = await self._measure_workspace(
            config=config,
            patch=incumbent_patch,
            phase=f"baseline-{iteration}",
        )
        request = CandidateRequest(
            campaign_id=config.campaign_id,
            iteration=iteration,
            objective=config.objective,
            test_command=config.test_command,
            benchmark_command=config.benchmark_command,
            baseline_test=baseline_test,
            baseline_benchmark=baseline_benchmark,
            prior_feedback=self.store.last_trial_feedback(),
        )
        proposal_workspace = self._workspace(config, state.base_commit, incumbent_patch)
        try:
            proposal = await self.provider.propose(_ProposalWorkspaceView(proposal_workspace), request)
        except Exception as exc:
            proposal_workspace.close()
            failures = state.consecutive_provider_failures + 1
            status = (
                CampaignStatus.PROVIDER_UNAVAILABLE
                if failures >= config.provider_failure_limit
                else CampaignStatus.RUNNING
            )
            updated = replace(
                state,
                status=status,
                consecutive_provider_failures=failures,
                last_error=str(exc),
                updated_at=_now(),
            )
            self.store.save_state(updated)
            self.store.append_event(
                {
                    "type": "provider_failure",
                    "iteration": iteration,
                    "error": str(exc),
                    "consecutive_failures": failures,
                    "recorded_at": _now(),
                }
            )
            return updated
        try:
            candidate_patch = proposal_workspace.diff()
        finally:
            proposal_workspace.close()
        if not candidate_patch.strip():
            return self._record_rejection(
                state=state,
                iteration=iteration,
                reason="provider produced no code changes",
                candidate_patch_file=None,
            )
        protected = _protected_paths_touched(candidate_patch, config.protected_paths)
        candidate_file = self.store.save_candidate(iteration, candidate_patch, proposal)
        if protected:
            return self._record_rejection(
                state=state,
                iteration=iteration,
                reason=f"candidate touched protected paths: {', '.join(protected)}",
                candidate_patch_file=candidate_file,
            )

        candidate_test, candidate_benchmark = await self._measure_workspace(
            config=config,
            patch=candidate_patch,
            phase=f"candidate-{iteration}",
        )
        decision = _decide_trial(
            baseline_test=baseline_test,
            candidate_test=candidate_test,
            baseline_benchmark=baseline_benchmark,
            candidate_benchmark=candidate_benchmark,
            minimum_speedup=config.minimum_speedup,
        )
        if decision.accepted and self._warden is not None:
            from maistro_rsi.quarantine import quarantine_scan
            from maistro_rsi.selfbranch import paths_touched_by_diff

            quarantine = await quarantine_scan(
                candidate_patch,
                paths_touched_by_diff(candidate_patch),
                self._warden,
                adversarial_review=self._adversarial_review,
            )
            self.store.append_event(
                {
                    "type": "quarantine",
                    "iteration": iteration,
                    "cleared": quarantine.cleared,
                    "requires_adversarial_review": quarantine.requires_adversarial_review,
                    "flags": list(quarantine.flags),
                    "reason": quarantine.reason,
                    "recorded_at": _now(),
                }
            )
            if not quarantine.cleared:
                return self._record_rejection(
                    state=state,
                    iteration=iteration,
                    reason=f"quarantine: {quarantine.reason or 'not cleared'}",
                    candidate_patch_file=candidate_file,
                )

        if decision.accepted:
            self.store.accept_candidate(candidate_patch)
        updated = replace(
            state,
            iteration=iteration,
            accepted_candidates=state.accepted_candidates + int(decision.accepted),
            consecutive_provider_failures=0,
            last_error=None,
            updated_at=_now(),
        )
        self.store.save_state(updated)
        self.store.append_event(
            {
                "type": "trial",
                "iteration": iteration,
                "accepted": decision.accepted,
                "reason": decision.reason,
                "candidate_patch_file": candidate_file,
                "promotion_eligible": False,
                "recorded_at": _now(),
            }
        )
        return updated

    def _record_rejection(
        self,
        *,
        state: CampaignState,
        iteration: int,
        reason: str,
        candidate_patch_file: str | None,
    ) -> CampaignState:
        updated = replace(
            state,
            iteration=iteration,
            consecutive_provider_failures=0,
            last_error=None,
            updated_at=_now(),
        )
        self.store.save_state(updated)
        self.store.append_event(
            {
                "type": "trial",
                "iteration": iteration,
                "accepted": False,
                "reason": reason,
                "candidate_patch_file": candidate_patch_file,
                "promotion_eligible": False,
                "recorded_at": _now(),
            }
        )
        return updated

    def _workspace(
        self, config: CampaignConfig, base_commit: str, patch: str
    ) -> CampaignWorkspace:
        return self.workspace_factory(
            repo_url=config.repo_url,
            patch=patch or None,
            base_commit=base_commit,
            base_ref=None,
            image_ref=config.sandbox_image,
        )

    async def _measure_workspace(
        self, *, config: CampaignConfig, patch: str, phase: str
    ) -> tuple[CommandMeasurement, CommandMeasurement | None]:
        state = self.store.load_state()
        assert state.base_commit is not None
        workspace = self._workspace(config, state.base_commit, patch)

        async def execute(command: str, timeout: int) -> tuple[int, str]:
            result = workspace.run_command_result(command, timeout=timeout)
            return result.exit_code, f"{result.stdout}{result.stderr}"

        try:
            test = await measure_command(
                execute,
                phase=f"{phase}-test",
                command=config.test_command,
                timeout_seconds=config.command_timeout_seconds,
            )
            self.store.ledger.append_measurement(test)
            benchmark = None
            if config.benchmark_command is not None:
                benchmark = await measure_command(
                    execute,
                    phase=f"{phase}-benchmark",
                    command=config.benchmark_command,
                    timeout_seconds=config.command_timeout_seconds,
                    scorer=_real_benchmark_score,
                )
                self.store.ledger.append_measurement(benchmark)
            return test, benchmark
        finally:
            workspace.close()


def _decide_trial(
    *,
    baseline_test: CommandMeasurement,
    candidate_test: CommandMeasurement,
    baseline_benchmark: CommandMeasurement | None,
    candidate_benchmark: CommandMeasurement | None,
    minimum_speedup: float | None,
) -> ExperimentDecision:
    if not candidate_test.passed:
        return ExperimentDecision(False, "candidate test command failed", baseline_test, candidate_test)
    if baseline_benchmark is not None or candidate_benchmark is not None:
        if baseline_benchmark is None or candidate_benchmark is None:
            return ExperimentDecision(
                False, "benchmark evidence incomplete", baseline_test, candidate_test
            )
        return decide_candidate(
            baseline_benchmark,
            candidate_benchmark,
            minimum_speedup=minimum_speedup if minimum_speedup is not None else 1.0,
        )
    return decide_candidate(
        baseline_test,
        candidate_test,
        minimum_speedup=minimum_speedup if minimum_speedup is not None else 1.0,
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


class _ProposalWorkspaceView:
    """Capability view that cannot execute code, export patches, or close the VM."""

    def __init__(self, workspace: CampaignWorkspace) -> None:
        self._workspace = workspace

    def read_file(self, path: str) -> str:
        return self._workspace.read_file(self._validate_path(path))

    def write_file(self, path: str, content: str) -> None:
        self._workspace.write_file(self._validate_path(path), content)

    def delete_file(self, path: str) -> None:
        self._workspace.delete_file(self._validate_path(path))

    def search(self, pattern: str, *, glob: str = "**/*.py") -> list[str]:
        self._validate_path(glob)
        return self._workspace.search(pattern, glob=glob)

    def list_files(self, *, glob: str = "**/*", limit: int = 2000) -> list[str]:
        self._validate_path(glob)
        return self._workspace.list_files(glob=glob, limit=limit)

    @staticmethod
    def _validate_path(path: str) -> str:
        if ".git" in path.replace("\\", "/").split("/"):
            raise ValueError("Candidate provider may not access Git metadata")
        return path


def _protected_paths_touched(patch: str, protected_paths: tuple[str, ...]) -> tuple[str, ...]:
    protected = tuple(path.rstrip("/").replace("\\", "/") for path in protected_paths)
    touched: list[str] = []
    for line in patch.splitlines():
        if not line.startswith("diff --git a/"):
            continue
        path = line.removeprefix("diff --git a/").split(" b/", 1)[0]
        if any(path == item or path.startswith(f"{item}/") for item in protected):
            touched.append(path)
    return tuple(dict.fromkeys(touched))


def _real_benchmark_score(exit_code: int, output: str, _duration: float) -> float:
    """Read a real benchmark score from the command's final JSON line."""
    if exit_code != 0:
        return -1e308
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return -1e308
    try:
        result = json.loads(lines[-1])
    except json.JSONDecodeError:
        return -1e308
    if not isinstance(result, dict) or result.get("fidelity") != "real":
        return -1e308
    score = result.get("score")
    if isinstance(score, bool) or not isinstance(score, int | float):
        return float("-inf")
    return float(score)
