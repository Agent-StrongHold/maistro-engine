---
id: ADR-097
title: Secure default Linux install - Ubuntu VM with Docker Sandboxes
repo: maistro-engine
kind: adr
status: Accepted
created: 2026-06-12
substrate:
  - maistro-engine#ADR-093
implements: []
related:
  - maistro-engine#SPEC-180
  - maistro-engine#SPEC-190
  - maistro-engine#SPEC-207
  - maistro-engine#ADR-098
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests: []
layer: Governance
owners:
  - '@BlakeMatthews-dev'
---

# ADR-097: Secure Default Linux Install

## Context

Maistro needs one simple, safe, supportable Linux installation path. Selecting a different sandbox
substrate for every Linux distribution, hypervisor, and cloud makes installation difficult to test
and makes the security guarantee depend on environment-specific behavior.

Docker Sandboxes provides the product-shaped behavior Maistro needs for local autonomous builders:
hardware-VM isolation, private workspaces, persistence, controlled networking, and an isolated Docker
daemon inside each sandbox. On Linux it requires a supported Ubuntu host and KVM. When Maistro itself
runs in a virtual machine, the outer hypervisor must expose nested virtualization.

## Decision

The official simple Linux installation target is:

```text
Linux host or hypervisor
└── Ubuntu Server 24.04 LTS x86-64 VM
    ├── complete Maistro installation
    └── Docker Sandbox microVMs
        └── builders, RSI/Evolve candidates, and executable benchmarks
```

1. The complete Maistro installation runs inside the Ubuntu VM. The installer does not run Maistro
   directly on, install Maistro packages on, or turn the hypervisor host into a worker.
2. The VM must expose working KVM/nested virtualization. The guest installer verifies the supported
   Ubuntu release, architecture, `/dev/kvm`, virtualization capability, Docker Sandboxes availability,
   and required Docker authentication before enabling untrusted execution.
3. Failure of any required preflight check fails closed. The installer does not silently downgrade
   builders to a shared-kernel container or host subprocess.
4. On Proxmox, the default helper has one job: create and configure this Ubuntu VM, then invoke the
   common guest installer inside it. It does not create sibling builder VMs, use LXC, or leave a
   Maistro control daemon running on the Proxmox host.
5. On other Linux environments, operators provision the same Ubuntu VM using their available
   hypervisor and run the common guest installer.
6. Windows and macOS use the containerized desktop architecture and narrow host broker defined by
   ADR-098 and SPEC-208. They do not run the Maistro application as native host processes.
7. Docker Sandboxes uses clone mode only against a sanitized controller staging repository rebuilt
   from the pinned base plus accepted patch. It never receives the live host checkout. After
   creation, Maistro disables push URLs and verifies that no Git or control-plane credentials crossed
   the boundary. The host Docker socket is never exposed.

## Backlogged Alternatives

The sandbox protocol remains pluggable, but these are opt-in future providers rather than branches in
the simple default installer:

- Proxmox API-managed sibling builder VMs
- Incus or libvirt/KVM builder VMs
- gVisor
- Kata Containers
- Firecracker or another dedicated microVM manager
- E2B or another managed sandbox service
- Hardened rootless Podman/Docker for explicitly trusted workloads only

An alternative provider must pass the same sandbox conformance suite and report its actual isolation
tier. Custom and high-scale deployments may choose a different provider explicitly; they do not
change the simple installer's default.

## Consequences

### Positive

- One Linux environment can be documented, tested, and supported end to end.
- Proxmox and other hypervisor users get the same Maistro runtime.
- Untrusted builders are separated from both the Maistro control plane and the physical host by
  virtualization boundaries.
- Nested Docker and benchmark workloads run inside the sandbox rather than through the host socket.

### Negative / Trade-offs

- Nested virtualization is mandatory for the recommended VM deployment.
- The extra virtualization layer adds startup, memory, and some I/O overhead.
- Linux hosts that cannot provide a supported Ubuntu VM with KVM cannot use the safe default path.
- Docker Sandboxes availability, authentication, and product lifecycle become dependencies of the
  default installer.

## Current Implementation Status

This decision is accepted, but the installer, Proxmox helper, and Docker Sandboxes backend are not
implemented yet. Until the preflight, adapter, and conformance tests pass, documentation and release
artifacts must describe this as the target default rather than a working production install.

## Acceptance Criteria

- The guest installer emits or applies a Docker Sandboxes deployment plan only after all required
  preflight checks pass.
- The Proxmox helper only provisions the Ubuntu VM and invokes the common guest installer.
- A clean Ubuntu Server VM installation test exercises nested KVM and starts a sandbox.
- Builders, RSI/Evolve candidates, and executable benchmarks all use the central sandbox protocol
  through the Docker Sandboxes backend.
- Conformance tests prove no live host repository mount, no host Docker socket, disabled push URLs,
  no inherited credentials, default-deny execution networking, resource limits, artifact export,
  stop/resume, and teardown.
- Unsupported Linux environments receive a clear VM provisioning requirement, not an automatic
  lower-isolation fallback.

## References

- [Docker Sandboxes: get started and prerequisites](https://docs.docker.com/ai/sandboxes/get-started/)
- [Docker Sandboxes: usage, clone mode, lifecycle, and persistence](https://docs.docker.com/ai/sandboxes/usage/)
- [Docker Sandboxes: architecture](https://docs.docker.com/ai/sandboxes/architecture/)
