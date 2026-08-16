from __future__ import annotations

from typing import Any

import pytest

from maistro.graph import Graph, Node
from maistro.projects.scope_store import InMemoryProjectScopeStore
from maistro.runs import (
    AttemptExecutionService,
    AttemptLifecycleReconciler,
    InMemoryRunStore,
)
from maistro.runtime import PythonExecutionRuntime


@pytest.mark.asyncio
async def test_reconciling_same_completed_attempt_preserves_original_acceptance() -> None:
    projects = InMemoryProjectScopeStore()
    root = await projects.create_root("ws-1")
    project = await projects.create(
        workspace_id="ws-1",
        parent_project_id=root.project_id,
        name="Idempotence",
    )
    store = InMemoryRunStore(project_store=projects)
    graph = Graph(
        workspace_id="ws-1",
        project_id=project.project_id,
        name="One node",
        nodes=[Node(node_id="node-1", node_type="agent")],
    )
    run = await store.create_run(graph)
    node_run = await store.create_node_run(run.run_id, node_id="node-1")
    service = AttemptExecutionService(store=store, runtime=PythonExecutionRuntime())

    async def executor(_work_item: Any, _context: Any) -> str:
        return "ok"

    terminal = await service.execute(node_run.node_run_id, None, None, executor=executor)
    first = await store.get_node_run(node_run.node_run_id)
    assert first is not None and first.accepted_outcome is not None

    reconciled = await AttemptLifecycleReconciler(store).reconcile(terminal)

    assert reconciled.accepted_outcome == first.accepted_outcome
