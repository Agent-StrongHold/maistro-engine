from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from maistro.graph.durable_runs.stores import InMemoryDurableRunStore
from maistro.graph.nodes.base import BaseNode, NodeContext, pause_until
from maistro.runtime import ExecutionRuntime, RunKind, RunState, WorkspaceRef


class EmptyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DoneOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    done: bool = True


class DoneNode(BaseNode[EmptyIn, DoneOut]):
    kind: ClassVar[str] = "test.done"
    input_schema: ClassVar[type[BaseModel]] = EmptyIn
    output_schema: ClassVar[type[BaseModel]] = DoneOut

    async def _execute(self, inputs: EmptyIn, ctx: NodeContext) -> DoneOut:
        return DoneOut()


class PauseOnceNode(BaseNode[EmptyIn, DoneOut]):
    kind: ClassVar[str] = "test.pause_once"
    kind_category = "wait"
    input_schema: ClassVar[type[BaseModel]] = EmptyIn
    output_schema: ClassVar[type[BaseModel]] = DoneOut

    def __init__(self) -> None:
        self.calls = 0

    async def _execute(self, inputs: EmptyIn, ctx: NodeContext) -> DoneOut:
        self.calls += 1
        if self.calls == 1:
            pause_until("external_wait")
        return DoneOut()


def _dag(kind: str) -> dict[str, object]:
    return {
        "id": "runtime-contract-dag",
        "entry_node": "n1",
        "nodes": [{"id": "n1", "kind": kind}],
        "edges": [],
    }


@pytest.mark.asyncio
@pytest.mark.contract("behavioral")
@pytest.mark.scope("integration")
async def test_run_graph_uses_one_canonical_workspace_owned_identity() -> None:
    store = InMemoryDurableRunStore()
    runtime = ExecutionRuntime(durable_run_store=store)
    node = DoneNode()

    result = await runtime.run_graph(
        _dag(node.kind),
        workspace=WorkspaceRef(workspace_id="workspace-1", actor_id="user-1"),
        node_resolver=lambda _node_id, _dag: node,
        run_id="run-1",
        correlation_id="trace-1",
        metadata={"source": "contract-test"},
    )

    persisted = await store.get("run-1")
    assert persisted is not None
    assert result.context.run_id == result.durable.run_id == persisted.run_id == "run-1"
    assert result.context.workspace_id == persisted.project_id == "workspace-1"
    assert result.context.run.state == RunState.COMPLETED
    assert persisted.root_run_id == "run-1"
    assert persisted.parent_run_id is None
    assert persisted.correlation_id == "trace-1"
    assert persisted.runtime_metadata == {"source": "contract-test"}


@pytest.mark.asyncio
@pytest.mark.contract("behavioral")
@pytest.mark.scope("integration")
async def test_resume_preserves_workspace_and_canonical_lineage() -> None:
    store = InMemoryDurableRunStore()
    runtime = ExecutionRuntime(durable_run_store=store)
    node = PauseOnceNode()
    resolver = lambda _node_id, _dag: node

    paused = await runtime.run_graph(
        _dag(node.kind),
        workspace=WorkspaceRef(workspace_id="workspace-1", actor_id="user-1"),
        node_resolver=resolver,
        run_id="run-pause",
        correlation_id="trace-pause",
    )
    assert paused.context.run.state == RunState.PAUSED

    resumed = await runtime.resume_graph("run-pause", node_resolver=resolver)

    assert resumed.context.run.state == RunState.COMPLETED
    assert resumed.context.run_id == "run-pause"
    assert resumed.context.workspace_id == "workspace-1"
    assert resumed.context.root_run_id == "run-pause"
    assert resumed.context.parent_run_id is None
    assert resumed.context.correlation_id == "trace-pause"
    assert resumed.durable.project_id == "workspace-1"


@pytest.mark.asyncio
@pytest.mark.contract("behavioral")
@pytest.mark.scope("integration")
async def test_child_graph_persists_parent_root_and_correlation() -> None:
    store = InMemoryDurableRunStore()
    runtime = ExecutionRuntime(durable_run_store=store)
    root = runtime.root_context(
        WorkspaceRef(workspace_id="workspace-1", actor_id="user-1"),
        kind=RunKind.AGENT,
        run_id="root-agent",
        correlation_id="trace-root",
    )
    node = DoneNode()

    child = await runtime.run_graph(
        _dag(node.kind),
        parent=root,
        node_resolver=lambda _node_id, _dag: node,
        run_id="child-graph",
    )

    assert child.context.run_id == "child-graph"
    assert child.context.parent_run_id == "root-agent"
    assert child.context.root_run_id == "root-agent"
    assert child.context.workspace_id == "workspace-1"
    assert child.context.correlation_id == "trace-root"
    assert child.durable.parent_run_id == "root-agent"
    assert child.durable.root_run_id == "root-agent"
    assert child.durable.correlation_id == "trace-root"
