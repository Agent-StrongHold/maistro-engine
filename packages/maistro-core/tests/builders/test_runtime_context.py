"""Tests for BuildersRuntime context enforcement — SPEC-200."""

from __future__ import annotations

import pytest

from maistro.builders.contracts import (
    ExecutionContext,
    RunRequest,
    RunResult,
    RunStatus,
    WorkerName,
)
from maistro.builders.errors import ContextViolation
from maistro.builders.runtime import BuildersRuntime

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request(worker: WorkerName = WorkerName.MASON, stage: str = "tests_written") -> RunRequest:
    return RunRequest(
        run_id="run-1",
        worker=worker,
        stage=stage,
        repo="owner/repo",
        issue_number=1,
        branch="feat/x",
        workspace_ref="ws_abc",
    )


async def _ok_handler(req: RunRequest) -> RunResult:
    return RunResult(
        run_id=req.run_id,
        worker=req.worker,
        stage=req.stage,
        status=RunStatus.PASSED,
        summary="ok",
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_stores_context(self) -> None:
        rt = BuildersRuntime()
        rt.register(
            WorkerName.MASON, "tests_written", _ok_handler, context=ExecutionContext.SANDBOX
        )
        assert rt.declared_context(WorkerName.MASON, "tests_written") == ExecutionContext.SANDBOX

    def test_declared_context_none_for_unregistered(self) -> None:
        rt = BuildersRuntime()
        assert rt.declared_context(WorkerName.MASON, "nonexistent") is None

    def test_register_all_contexts(self) -> None:
        rt = BuildersRuntime()
        for ctx in ExecutionContext:
            rt.register(WorkerName.FRANK, ctx.value, _ok_handler, context=ctx)
            assert rt.declared_context(WorkerName.FRANK, ctx.value) == ctx

    def test_supports_returns_true_after_register(self) -> None:
        rt = BuildersRuntime()
        rt.register(WorkerName.AUDITOR, "review", _ok_handler, context=ExecutionContext.SANDBOX)
        assert rt.supports(WorkerName.AUDITOR, "review") is True

    def test_supports_returns_false_before_register(self) -> None:
        rt = BuildersRuntime()
        assert rt.supports(WorkerName.AUDITOR, "review") is False

    def test_all_new_worker_names_registerable(self) -> None:
        rt = BuildersRuntime()
        for worker in WorkerName:
            rt.register(worker, "stage", _ok_handler, context=ExecutionContext.CONVERSATION)
        for worker in WorkerName:
            assert rt.supports(worker, "stage")


# ---------------------------------------------------------------------------
# Context enforcement in execute()
# ---------------------------------------------------------------------------


class TestContextEnforcement:
    @pytest.mark.asyncio
    async def test_matching_context_executes_handler(self) -> None:
        rt = BuildersRuntime()
        rt.register(
            WorkerName.MASON, "tests_written", _ok_handler, context=ExecutionContext.SANDBOX
        )
        result = await rt.execute(_request(), active_context=ExecutionContext.SANDBOX)
        assert result.status == RunStatus.PASSED

    @pytest.mark.asyncio
    async def test_wrong_context_raises_context_violation(self) -> None:
        rt = BuildersRuntime()
        rt.register(
            WorkerName.MASON, "tests_written", _ok_handler, context=ExecutionContext.SANDBOX
        )
        with pytest.raises(ContextViolation) as exc_info:
            await rt.execute(_request(), active_context=ExecutionContext.REPO)
        assert exc_info.value.agent == WorkerName.MASON.value
        assert exc_info.value.declared == ExecutionContext.SANDBOX.value
        assert exc_info.value.attempted == ExecutionContext.REPO.value

    @pytest.mark.asyncio
    async def test_no_active_context_skips_enforcement(self) -> None:
        rt = BuildersRuntime()
        rt.register(
            WorkerName.MASON, "tests_written", _ok_handler, context=ExecutionContext.SANDBOX
        )
        # No active_context → no enforcement; handler runs
        result = await rt.execute(_request(), active_context=None)
        assert result.status == RunStatus.PASSED

    @pytest.mark.asyncio
    async def test_unregistered_stage_returns_failed_result(self) -> None:
        rt = BuildersRuntime()
        result = await rt.execute(_request(stage="nonexistent"))
        assert result.status == RunStatus.FAILED
        assert "Unsupported" in result.summary

    @pytest.mark.asyncio
    async def test_conversation_context_enforced(self) -> None:
        rt = BuildersRuntime()
        rt.register(
            WorkerName.ARBITER,
            "clarify",
            _ok_handler,
            context=ExecutionContext.CONVERSATION,
        )
        req = RunRequest(
            run_id="r",
            worker=WorkerName.ARBITER,
            stage="clarify",
            repo="r/r",
            issue_number=0,
            branch="b",
            workspace_ref="ws",
        )
        with pytest.raises(ContextViolation):
            await rt.execute(req, active_context=ExecutionContext.SANDBOX)

    @pytest.mark.asyncio
    async def test_janitor_repo_context_enforced(self) -> None:
        rt = BuildersRuntime()
        rt.register(
            WorkerName.JANITOR,
            "cleanup",
            _ok_handler,
            context=ExecutionContext.REPO,
        )
        req = RunRequest(
            run_id="r",
            worker=WorkerName.JANITOR,
            stage="cleanup",
            repo="r/r",
            issue_number=0,
            branch="b",
            workspace_ref="ws",
        )
        # Correct context passes
        result = await rt.execute(req, active_context=ExecutionContext.REPO)
        assert result.status == RunStatus.PASSED

        # Wrong context raises
        with pytest.raises(ContextViolation):
            await rt.execute(req, active_context=ExecutionContext.SANDBOX)


# ---------------------------------------------------------------------------
# ContextViolation error fields
# ---------------------------------------------------------------------------


class TestContextViolationError:
    def test_fields_accessible(self) -> None:
        err = ContextViolation("mason", "sandbox", "repo")
        assert err.agent == "mason"
        assert err.declared == "sandbox"
        assert err.attempted == "repo"

    def test_str_contains_all_three(self) -> None:
        err = ContextViolation("mason", "sandbox", "repo")
        s = str(err)
        assert "mason" in s
        assert "sandbox" in s
        assert "repo" in s
