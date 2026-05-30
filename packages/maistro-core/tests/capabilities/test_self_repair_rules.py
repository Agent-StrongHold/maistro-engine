"""Diagnosis rule table — symptom → candidate remediation (SPEC-188).

`diagnose()` is pure: InfraHealth in, RepairProposals out, no side effects. It
reads per-entity detail under each section (containers/stacks/units/vms/servers/
pools) and emits one proposal per problem entity. Healthy entities → nothing.
"""

from __future__ import annotations

from maistro.capabilities.self_repair_rules import diagnose
from maistro.capabilities.slots.infra import InfraHealth, ResourceHealth


def _health(**sections: ResourceHealth) -> InfraHealth:
    return InfraHealth(ts="2026-05-30T00:00:00Z", resources=dict(sections))


def test_healthy_snapshot_yields_no_proposals() -> None:
    health = _health(
        docker=ResourceHealth("ok", {"containers": [{"name": "litellm", "status": "running"}]}),
        storage=ResourceHealth("ok", {"pools": [{"name": "dbpool", "status": "online"}]}),
    )
    assert diagnose(health) == []


def test_down_container_proposes_restart_container_reversible() -> None:
    health = _health(
        docker=ResourceHealth("degraded", {"containers": [{"name": "litellm", "status": "down"}]})
    )
    (p,) = diagnose(health)
    assert p.resource == "docker:litellm"
    assert p.action == "restart_container"
    assert p.params == {"name": "litellm"}
    assert p.tier == "reversible"
    assert p.recognized is True


def test_unhealthy_container_also_proposes_restart() -> None:
    health = _health(
        docker=ResourceHealth("degraded", {"containers": [{"name": "api", "status": "unhealthy"}]})
    )
    (p,) = diagnose(health)
    assert p.action == "restart_container"


def test_down_stack_proposes_restart_stack_destructive() -> None:
    health = _health(
        docker=ResourceHealth("down", {"stacks": [{"project": "media", "status": "down"}]})
    )
    (p,) = diagnose(health)
    assert p.resource == "stack:media"
    assert p.action == "restart_stack"
    assert p.params == {"project": "media"}
    assert p.tier == "destructive"


def test_failed_service_proposes_restart_service() -> None:
    health = _health(
        services=ResourceHealth("degraded", {"units": [{"name": "tailscaled", "status": "failed"}]})
    )
    (p,) = diagnose(health)
    assert p.resource == "service:tailscaled"
    assert p.action == "restart_service"
    assert p.params == {"name": "tailscaled"}
    assert p.tier == "reversible"


def test_stopped_vm_expected_running_proposes_vm_start() -> None:
    health = _health(
        vms=ResourceHealth("degraded", {"vms": [{"vmid": 101, "status": "stopped", "expected": "running"}]})
    )
    (p,) = diagnose(health)
    assert p.resource == "vm:101"
    assert p.action == "vm_control"
    assert p.params == {"vmid": 101, "action": "start"}
    assert p.tier == "reversible"


def test_stopped_vm_not_expected_running_is_ignored() -> None:
    health = _health(
        vms=ResourceHealth("ok", {"vms": [{"vmid": 200, "status": "stopped", "expected": "stopped"}]})
    )
    assert diagnose(health) == []


def test_unreachable_gpu_server_proposes_restart_container() -> None:
    health = _health(
        gpu=ResourceHealth("degraded", {"servers": [{"name": "ollama", "reachable": False}]})
    )
    (p,) = diagnose(health)
    assert p.resource == "gpu:ollama"
    assert p.action == "restart_container"
    assert p.params == {"name": "ollama"}


def test_degraded_storage_is_propose_only() -> None:
    health = _health(
        storage=ResourceHealth("degraded", {"pools": [{"name": "dbpool", "status": "degraded"}]})
    )
    (p,) = diagnose(health)
    assert p.resource == "storage:dbpool"
    assert p.action is None          # never auto-acted — data risk
    assert p.recognized is True       # but it IS recognized → propose-only, not undiagnosed
    assert "dbpool" in p.rationale


def test_degraded_section_with_no_known_entity_is_undiagnosed() -> None:
    health = _health(
        docker=ResourceHealth("down", {"weird": "shape"})  # degraded but nothing recognizable
    )
    (p,) = diagnose(health)
    assert p.action is None
    assert p.recognized is False      # undiagnosed → escalate to human


def test_multiple_problems_yield_multiple_proposals() -> None:
    health = _health(
        docker=ResourceHealth("degraded", {"containers": [
            {"name": "a", "status": "down"},
            {"name": "b", "status": "running"},
            {"name": "c", "status": "exited"},
        ]}),
        services=ResourceHealth("degraded", {"units": [{"name": "svc", "status": "failed"}]}),
    )
    resources = sorted(p.resource for p in diagnose(health))
    assert resources == ["docker:a", "docker:c", "service:svc"]
