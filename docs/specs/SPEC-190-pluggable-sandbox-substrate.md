---
id: SPEC-190
title: Pluggable sandbox substrate - Docker Sandboxes default with optional providers
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-05-31
substrate:
  - maistro-engine#ADR-093
  - maistro-engine#ADR-097
implements:
  - maistro-engine#ADR-093
  - maistro-engine#ADR-097
related:
  - maistro-engine#SPEC-184
  - maistro-engine#SPEC-012
  - maistro-engine#SPEC-011
  - maistro-engine#SPEC-013
  - maistro-engine#SPEC-207
  - maistro-engine#ADR-098
  - maistro-engine#SPEC-208
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests: []
layer: Tools
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-190: Pluggable Sandbox Substrate

## Context

Per ADR-093, untrusted agent/tool code must run behind a hardware-VM boundary, and the substrate must
sit behind a protocol rather than being hardwired to Docker. The legacy
`maistro.tools.sandbox.docker` implementation shells out to the Docker CLI and assumes a reachable
Docker socket. That is not an acceptable production boundary.

ADR-097 and ADR-098 select Docker Sandboxes as the official simple installer backend. Linux invokes
the adapter inside the Ubuntu VM. Windows/macOS control-plane containers invoke it through the
narrow host broker in SPEC-208. This spec defines the common protocol and conformance contract.

## Goals

- A `SandboxProtocol` that all sandbox callers depend on.
- A Docker Sandboxes microVM backend satisfying ADR-093 and ADR-097.
- A conformance suite, including escape and containment assertions, that every backend must pass.
- Safe backend selection that fails closed when the required isolation is unavailable.
- An honest transition path for legacy container behavior used only by trusted development flows.

## Non-goals

- Implementing every possible Linux, cloud, or hypervisor backend in the default installer.
- Image supply-chain hardening, which is a separate track.
- A general container orchestrator.
- Hyperlight or wasm execution in the first implementation.

## Protocol Sketch

```python
class SandboxHandle(Protocol):
    id: str
    async def exec(self, argv: list[str], *, timeout_s: float, stdin: bytes | None = None) -> ExecResult: ...
    async def write_file(self, path: str, data: bytes) -> None: ...
    async def read_file(self, path: str) -> bytes: ...
    async def stop(self) -> None: ...

class SandboxProtocol(Protocol):
    async def spawn(self, spec: SandboxSpec) -> SandboxHandle: ...
    def capabilities(self) -> SandboxCapabilities: ...

@dataclass(frozen=True)
class SandboxSpec:
    image_ref: str
    workspace: WorkspaceMount
    network: NetPolicy
    limits: ResourceLimits
    env: Mapping[str, str]
```

`SandboxCapabilities.isolation` reports the actual boundary. Callers handling untrusted input assert
VM-grade isolation before execution.

## Providers

| Backend | Isolation | KVM required | Status |
|---------|-----------|--------------|--------|
| `docker-sandboxes` | VM | yes | Official installer default; implement first |
| `container` (rootless, no host socket) | Shared kernel | no | Transition/dev only |
| `proxmox-vm` / `incus-vm` / `libvirt-vm` | VM | host-specific | Backlog |
| `gvisor` | Hardened shared kernel | no | Backlog |
| `kata` | VM | yes | Backlog |
| `firecracker` | VM | yes | Backlog |
| `hyperlight` | VM-style bounded guest | yes | Future |

The default installer does not branch across these providers. Custom deployments may select an
implemented provider explicitly after it passes conformance.

## Docker Sandboxes Contract

- Use clone mode only against a sanitized staging repository reconstructed from the pinned base plus
  accepted patch; never expose the live host working tree.
- Disable all push URLs and verify that Git and control-plane credentials are absent before candidate
  code executes.
- Never expose the host Docker socket.
- Keep control-plane credentials outside candidate-controlled sandboxes.
- Use a networked materialization phase and a separate default-deny execution phase.
- Export patches, artifacts, logs, and campaign state through the protocol.
- Support stop/resume or pinned-base-plus-patch replay without trusting mutable guest state.
- Report the actual backend and isolation tier in execution evidence.

## Wiring

Backends are registered through dependency injection and selected through `sandbox.backend`. The
official installer selects `docker-sandboxes`: directly inside the supported Linux VM envelope or
through the desktop broker. If Docker Sandboxes or the required virtualization substrate is
unavailable, untrusted execution refuses to start rather than silently falling back.

Explicit development configuration may select a weaker backend only for trusted workloads. Secrets
reach a sandbox only through the approved broker, never through the raw control-plane environment.

## Acceptance Criteria

- [ ] `SandboxProtocol`, `SandboxSpec`, and `SandboxHandle` are the only execution interface used by
      Builders, RSI/Evolve candidates, and executable benchmarks.
- [ ] A `FakeSandbox` backend supports unit tests.
- [ ] A Docker Sandboxes backend implements the protocol and private workspace behavior.
- [ ] Conformance covers network deny by default, no live host checkout, disabled push URLs, no
      inherited credentials, no host-path escape, no host Docker socket, resource limits, artifact
      export, persistence/replay, and teardown.
- [ ] Backend selection fails closed when a caller requests unavailable VM-grade isolation.
- [ ] Every result records the actual backend and isolation tier.

## Testing

- Protocol-level conformance tests are parametrized across implemented providers.
- VM-provider tests may skip only when the environment lacks the required substrate, and the skip is
  reported explicitly.
- Escape tests assert the sandbox cannot read a host marker, reach a host runtime socket, or egress
  outside policy.
- Property-based tests fuzz resource limits, environment, and paths at the protocol boundary.

## Backlog

- Proxmox API-managed sibling builder VMs.
- Incus and libvirt/KVM lifecycle providers.
- gVisor, Kata, Firecracker, Hyperlight, and managed sandbox providers.
- Provider-specific networking and snapshot optimization.
- High-density cloud and Kubernetes deployment profiles.

## References

- ADR-093 - sandbox isolation model.
- ADR-097 - secure default Linux install.
- SPEC-207 - secure default installer and Proxmox helper.
- ADR-098 and SPEC-208 - secure desktop install and host broker.
- `packages/maistro-core/src/maistro/sandbox/` - current central sandbox implementation.
- SPEC-011, SPEC-012, SPEC-013, and SPEC-184.
