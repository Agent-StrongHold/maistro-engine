"""Diagnosis rule table for self_repair (SPEC-188).

Pure: maps an InfraHealth snapshot to candidate RepairProposals via an explicit,
auditable table. Every emitted action is one already on the infra_action
allowlist — diagnosis never synthesizes new actions. Unknown symptoms produce an
``undiagnosed`` proposal (recognized=False) so the loop escalates rather than
guesses.

Input contract — per-section detail shapes this reads (others are ignored):
  docker   detail["containers"] = [{"name", "status"}]   status down/unhealthy/exited/dead
           detail["stacks"]     = [{"project", "status"}] status down
  services detail["units"]      = [{"name", "status"}]    status failed
  vms      detail["vms"]        = [{"vmid", "status", "expected"}]  stopped & expected running
  gpu      detail["servers"]    = [{"name", "reachable"}] reachable False
  storage  detail["pools"]      = [{"name", "status"}]    degraded/faulted  → propose-only
"""

from __future__ import annotations

from typing import Any

from maistro.capabilities.slots.infra import ActionTier, InfraHealth
from maistro.capabilities.slots.self_repair import RepairProposal

_CONTAINER_BAD = {"down", "unhealthy", "exited", "dead"}
_UNIT_BAD = {"failed"}
_POOL_BAD = {"degraded", "faulted"}
_DEGRADED = {"degraded", "down"}


def diagnose(health: InfraHealth) -> list[RepairProposal]:
    """Return one proposal per problem entity in the snapshot (empty if healthy)."""
    proposals: list[RepairProposal] = []
    for section, resource in health.resources.items():
        before = len(proposals)
        proposals.extend(_diagnose_section(section, resource.detail))
        # Section flagged degraded/down but no entity matched a rule → undiagnosed.
        if before == len(proposals) and resource.status in _DEGRADED:
            proposals.append(
                RepairProposal(
                    resource=section,
                    symptom="undiagnosed",
                    action=None,
                    tier="",
                    rationale=f"{section} {resource.status} with no recognized cause",
                    recognized=False,
                )
            )
    return proposals


def _diagnose_section(section: str, detail: dict[str, Any]) -> list[RepairProposal]:
    handler = _SECTION_HANDLERS.get(section)
    return handler(detail) if handler is not None else []


def _items(detail: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = detail.get(key)
    return [i for i in value if isinstance(i, dict)] if isinstance(value, list) else []


def _diagnose_docker(detail: dict[str, Any]) -> list[RepairProposal]:
    out: list[RepairProposal] = []
    for c in _items(detail, "containers"):
        if str(c.get("status", "")).lower() in _CONTAINER_BAD:
            name = str(c.get("name", ""))
            out.append(RepairProposal(
                resource=f"docker:{name}", symptom=f"container {c.get('status')}",
                action="restart_container", params={"name": name},
                tier=ActionTier.REVERSIBLE.value, rationale=f"container {name} not running",
            ))
    for s in _items(detail, "stacks"):
        if str(s.get("status", "")).lower() == "down":
            project = str(s.get("project", ""))
            out.append(RepairProposal(
                resource=f"stack:{project}", symptom="stack down",
                action="restart_stack", params={"project": project},
                tier=ActionTier.DESTRUCTIVE.value, rationale=f"stack {project} down",
            ))
    return out


def _diagnose_services(detail: dict[str, Any]) -> list[RepairProposal]:
    out: list[RepairProposal] = []
    for u in _items(detail, "units"):
        if str(u.get("status", "")).lower() in _UNIT_BAD:
            name = str(u.get("name", ""))
            out.append(RepairProposal(
                resource=f"service:{name}", symptom="unit failed",
                action="restart_service", params={"name": name},
                tier=ActionTier.REVERSIBLE.value, rationale=f"systemd unit {name} failed",
            ))
    return out


def _diagnose_vms(detail: dict[str, Any]) -> list[RepairProposal]:
    out: list[RepairProposal] = []
    for vm in _items(detail, "vms"):
        stopped = str(vm.get("status", "")).lower() == "stopped"
        expected_running = str(vm.get("expected", "running")).lower() == "running"
        if stopped and expected_running:
            vmid = vm.get("vmid")
            out.append(RepairProposal(
                resource=f"vm:{vmid}", symptom="vm stopped",
                action="vm_control", params={"vmid": vmid, "action": "start"},
                tier=ActionTier.REVERSIBLE.value, rationale=f"vm {vmid} stopped, expected running",
            ))
    return out


def _diagnose_gpu(detail: dict[str, Any]) -> list[RepairProposal]:
    out: list[RepairProposal] = []
    for srv in _items(detail, "servers"):
        if srv.get("reachable") is False:
            name = str(srv.get("name", ""))
            out.append(RepairProposal(
                resource=f"gpu:{name}", symptom="model server unreachable",
                action="restart_container", params={"name": name},
                tier=ActionTier.REVERSIBLE.value, rationale=f"model server {name} unreachable",
            ))
    return out


def _diagnose_storage(detail: dict[str, Any]) -> list[RepairProposal]:
    # Storage degradation is data risk — recognized but never auto-acted.
    out: list[RepairProposal] = []
    for pool in _items(detail, "pools"):
        if str(pool.get("status", "")).lower() in _POOL_BAD:
            name = str(pool.get("name", ""))
            out.append(RepairProposal(
                resource=f"storage:{name}", symptom=f"zpool {pool.get('status')}",
                action=None, tier="",
                rationale=f"pool {name} {pool.get('status')} — human review (data risk)",
                recognized=True,
            ))
    return out


_SECTION_HANDLERS = {
    "docker": _diagnose_docker,
    "services": _diagnose_services,
    "vms": _diagnose_vms,
    "gpu": _diagnose_gpu,
    "storage": _diagnose_storage,
}
