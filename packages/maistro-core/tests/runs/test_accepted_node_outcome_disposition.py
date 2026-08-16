from __future__ import annotations

from typing import Any

import pytest

from maistro.graph import Graph, Node
from maistro.projects.scope_store import InMemoryProjectScopeStore
from maistro.runs import (
    AcceptedNodeOutcome,
    AttemptExecutionService,
    AttemptResult,
    AttemptStatus,
    InMemoryRunStore,
    RunStatus,
)
from maistro.runtime import PythonExecutionRuntime


async def _execution() -> tuple[InMemoryRunStore, str, AttemptExecutionService]:
    projects = InMemoryProjectScopeStore()
    root = await projects.create_root("ws-1")
    project = await projects.create(
        workspace_id="ws-1",
        parent_project_id=root.project_id,
        name="Disposition",
    )
    graph = Graph(
        workspace_id="ws-1",
        project_id=project.project_id,
        name="One node",
        nodes=[Node(node_id="node-1", node_type="agent")],
    )
    store = InMemoryRunStore(project_store=projects)
    run = await store.create_run(graph)
    node_run = await store.create_node_run(run.run_id, node_id="node-1")
    return store, node_run.node_run_id, AttemptExecutionService(
        store=store,
        runtime=PythonExecutionRuntime(),
    )


@pytest.mark.asyncio
async def test_physical_completion_can_wait_for_domain_acceptance() -> None:
    store, node_run_id, service = await _execution()

    async def executor(_work_item: Any, _context: Any) -> dict[str, str]:
        return {"status": "paused"}

    terminal = await service.execute(
        node_run_id,
        None,
        None,
        executor=executor,
        reconcile_completed=False,
    )

    assert terminal.status is AttemptStatus.COMPLETED
    logical = await store.get_node_run(node_run_id)
    assert logical is not None
    assert logical.status is RunStatus.RUNNING
    assert logical.accepted_outcome is None


@pytest.mark.asyncio
@pytest.mark.parametrize("logical_status", [RunStatus.PAUSED, RunStatus.WAITING, RunStatus.FAILED])
async def test_domain_can_accept_completed_physical_result_with_noncompleted_disposition(
    logical_status: RunStatus,
) -> None:
    store, node_run_id, service = await _execution()

    async def executor(_work_item: Any, _context: Any) -> dict[str, str]:
        return {"domain": logical_status.value}

    terminal = await service.execute(
        node_run_id,
        None,
        None,
        executor=executor,
        reconcile_completed=False,
    )
    outcome = AcceptedNodeOutcome(
        node_run_id=node_run_id,
        attempt_result=AttemptResult.from_attempt(terminal),
        logical_status=logical_status,
    )
    accepted = await store.transition_node_run(
        node_run_id,
        logical_status,
        result=terminal.result,
        error="logical failure" if logical_status is RunStatus.FAILED else None,
        accepted_outcome=outcome,
    )

    assert accepted.status is logical_status
    assert accepted.accepted_outcome == outcome
    assert accepted.result == terminal.result


@pytest.mark.asyncio
async def test_default_execution_still_accepts_simple_completed_result() -> None:
    store, node_run_id, service = await _execution()

    async def executor(_work_item: Any, _context: Any) -> str:
        return "ok"

    terminal = await service.execute(node_run_id, None, None, executor=executor)
    accepted = await store.get_node_run(node_run_id)

    assert terminal.status is AttemptStatus.COMPLETED
    assert accepted is not None and accepted.status is RunStatus.COMPLETED
    assert accepted.accepted_outcome is not None
    assert accepted.accepted_outcome.logical_status is RunStatus.COMPLETED
