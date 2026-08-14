from __future__ import annotations

import pytest

from maistro.graph import Graph, Node
from maistro.runs import (
    ActiveAttemptExists,
    AttemptStatus,
    InMemoryRunStore,
    RunIntegrityError,
    RunStatus,
)


def _graph(*, workspace_id: str = "workspace-1") -> Graph:
    return Graph(
        graph_id=f"graph-{workspace_id}",
        workspace_id=workspace_id,
        name="Pipeline",
        nodes=[
            Node(node_id="first", node_type="agent"),
            Node(node_id="second", node_type="transform"),
        ],
    )


@pytest.mark.asyncio
async def test_retry_creates_new_attempt_under_same_node_run_and_run() -> None:
    store = InMemoryRunStore()
    run = await store.create_run(_graph())
    await store.transition_run(run.run_id, RunStatus.QUEUED)
    await store.transition_run(run.run_id, RunStatus.RUNNING)

    node_run = await store.create_node_run(run.run_id, node_id="first")
    await store.transition_node_run(node_run.node_run_id, RunStatus.QUEUED)
    await store.transition_node_run(node_run.node_run_id, RunStatus.RUNNING)

    first = await store.create_attempt(node_run.node_run_id, executor_id="agent")
    await store.transition_attempt(first.attempt_id, AttemptStatus.RUNNING)
    await store.transition_attempt(first.attempt_id, AttemptStatus.FAILED, error="transient")

    second = await store.create_attempt(node_run.node_run_id, executor_id="agent")

    assert second.node_run_id == node_run.node_run_id
    assert second.ordinal == 2
    assert (await store.get_run(run.run_id)).run_id == run.run_id  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_node_run_allows_repeated_execution_of_same_graph_node() -> None:
    store = InMemoryRunStore()
    run = await store.create_run(_graph())

    first = await store.create_node_run(run.run_id, node_id="first")
    second = await store.create_node_run(run.run_id, node_id="first")

    assert first.node_run_id != second.node_run_id
    assert first.node_id == second.node_id == "first"
    assert (first.ordinal, second.ordinal) == (1, 2)


@pytest.mark.asyncio
async def test_node_run_must_reference_node_in_captured_graph() -> None:
    store = InMemoryRunStore()
    run = await store.create_run(_graph())

    with pytest.raises(RunIntegrityError, match="not present"):
        await store.create_node_run(run.run_id, node_id="missing")


@pytest.mark.asyncio
async def test_only_one_active_attempt_per_node_run() -> None:
    store = InMemoryRunStore()
    run = await store.create_run(_graph())
    node_run = await store.create_node_run(run.run_id, node_id="first")
    await store.create_attempt(node_run.node_run_id)

    with pytest.raises(ActiveAttemptExists):
        await store.create_attempt(node_run.node_run_id)


@pytest.mark.asyncio
async def test_child_run_requires_explicit_parent_correlation_and_same_workspace() -> None:
    store = InMemoryRunStore()
    parent = await store.create_run(_graph())
    parent_node = await store.create_node_run(parent.run_id, node_id="first")

    child = await store.create_run(
        _graph(),
        parent_run_id=parent.run_id,
        parent_node_run_id=parent_node.node_run_id,
    )

    assert child.parent_run_id == parent.run_id
    assert child.parent_node_run_id == parent_node.node_run_id

    with pytest.raises(RunIntegrityError, match="cross Workspace"):
        await store.create_run(
            _graph(workspace_id="workspace-2"),
            parent_run_id=parent.run_id,
        )


@pytest.mark.asyncio
async def test_parent_node_run_must_belong_to_declared_parent_run() -> None:
    store = InMemoryRunStore()
    first_parent = await store.create_run(_graph())
    second_parent = await store.create_run(_graph())
    second_parent_node = await store.create_node_run(second_parent.run_id, node_id="first")

    with pytest.raises(RunIntegrityError, match="does not belong"):
        await store.create_run(
            _graph(),
            parent_run_id=first_parent.run_id,
            parent_node_run_id=second_parent_node.node_run_id,
        )
