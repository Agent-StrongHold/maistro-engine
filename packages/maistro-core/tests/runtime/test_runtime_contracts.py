from __future__ import annotations

import pytest
from pydantic import ValidationError

from maistro.graph.durable_runs.stores import InMemoryDurableRunStore
from maistro.runtime import ExecutionRuntime, RunContext, RunKind, WorkspaceRef


@pytest.mark.contract("boundary")
@pytest.mark.scope("unit")
def test_workspace_ref_rejects_empty_id_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        WorkspaceRef(workspace_id="")
    with pytest.raises(ValidationError):
        WorkspaceRef(workspace_id="w1", unexpected=True)  # type: ignore[call-arg]


@pytest.mark.contract("behavioral")
@pytest.mark.scope("unit")
def test_root_context_owns_its_lineage_and_correlation() -> None:
    runtime = ExecutionRuntime(durable_run_store=InMemoryDurableRunStore())
    context = runtime.root_context(
        WorkspaceRef(workspace_id="workspace-1", actor_id="user-1"),
        kind=RunKind.MANUAL,
        run_id="root-1",
    )

    assert context.run_id == "root-1"
    assert context.root_run_id == "root-1"
    assert context.parent_run_id is None
    assert context.workspace_id == "workspace-1"
    assert context.actor_id == "user-1"
    assert context.correlation_id == "root-1"


@pytest.mark.contract("boundary")
@pytest.mark.scope("unit")
def test_top_level_run_cannot_claim_a_different_root() -> None:
    with pytest.raises(ValidationError):
        RunContext(
            run_id="run-1",
            workspace_id="w1",
            kind=RunKind.GRAPH,
            root_run_id="other-root",
            correlation_id="run-1",
        )


@pytest.mark.contract("behavioral")
@pytest.mark.scope("unit")
def test_child_context_preserves_workspace_root_actor_and_correlation() -> None:
    runtime = ExecutionRuntime(durable_run_store=InMemoryDurableRunStore())
    root = runtime.root_context(
        WorkspaceRef(workspace_id="workspace-1", actor_id="user-1"),
        kind=RunKind.AGENT,
        run_id="root-1",
        correlation_id="trace-99",
    )
    child = runtime.child_context(root, kind=RunKind.GRAPH, run_id="child-1")

    assert child.run_id == "child-1"
    assert child.parent_run_id == "root-1"
    assert child.root_run_id == "root-1"
    assert child.workspace_id == root.workspace_id
    assert child.actor_id == root.actor_id
    assert child.correlation_id == root.correlation_id


@pytest.mark.contract("behavioral")
@pytest.mark.scope("unit")
def test_child_cannot_be_its_own_parent() -> None:
    with pytest.raises(ValidationError):
        RunContext(
            run_id="same",
            workspace_id="w1",
            kind=RunKind.GRAPH,
            root_run_id="root",
            parent_run_id="same",
            correlation_id="root",
        )
