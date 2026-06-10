---
id: ADR-093
title: Sandbox isolation model — hardware-VM isolation for untrusted agent code
repo: maistro-engine
kind: adr
status: Accepted
created: 2026-05-31
substrate:
  - maistro-engine#ADR-019
  - maistro-engine#ADR-038
implements: []
related:
  - maistro-engine#SPEC-184
  - maistro-engine#SPEC-012
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
tests: []
layer: Governance
owners:
  - '@BlakeMatthews-dev'
history:
  - status: Proposed
    date: 2026-05-31
  - status: Accepted
    date: 2026-05-31
---

# ADR-093: Sandbox isolation model — hardware-VM isolation for untrusted agent code

## Context

The engine executes **untrusted, model-generated code** in several places: the tool sandbox
(`maistro.tools.sandbox`), tool execution in `chat_completion._execute_tool`, benchmark harnesses
that `exec()` generated code, and browser automation (browser-use / Playwright). Today this runs in
Docker containers, and the production image mounts the host Docker socket so the sandbox can spawn
sibling containers.

A shared-kernel container is a **namespace + seccomp + cgroup** boundary, not a security boundary
against hostile code: a single Linux kernel/syscall exploit crosses it. Worse, **a mounted Docker
socket is effectively root on the host** — code that reaches it can start a privileged container and
own the machine. We are, in effect, running adversarial input behind a boundary designed for
*resource isolation between cooperating processes*, not *containment of an attacker*.

## Problem

What isolation guarantee do we require for code we did not write and cannot trust, and is the current
container-with-socket model acceptable?

## Decision

1. **Untrusted agent/tool code MUST run behind a hardware-virtualization boundary (a microVM), not a
   shared-kernel container.** The trust boundary becomes the CPU's VM-exit / hypervisor, so a guest
   kernel or syscall exploit does not reach the host.
2. **The Docker-socket-mounting sandbox is deprecated for untrusted workloads.** Sharing the host
   Docker socket into a sandbox is prohibited; if a container runtime is retained transitionally it
   MUST be a rootless, socket-less, single-tenant configuration.
3. **Trusted first-party services keep container isolation.** The API server, hive-conductor backend,
   and other first-party services are not adversarial and continue to run as (distroless, non-root)
   containers. MicroVM isolation is reserved for the *sandbox* — where density is traded for
   containment deliberately.
4. **The substrate is an implementation detail behind a protocol.** No business logic depends on
   "Docker" or "Firecracker"; it depends on a `SandboxProtocol` (per the project's protocol-driven DI
   rule). The concrete backend (rootless container, Kata, Firecracker, Cloud Hypervisor, Hyperlight)
   is selected by configuration. The protocol and migration are specified in SPEC-190.

This is a **posture decision**, not a substrate mandate: it fixes the *required guarantee*
(hardware-VM containment for untrusted code) and forbids the *known-weak* configuration (shared Docker
socket). Which microVM technology satisfies the guarantee is SPEC-190's design space.

## Consequences

### Positive
- Adversarial code that escapes the guest hits a hypervisor boundary, not the host kernel.
- Removing the host Docker socket eliminates the single worst privilege-escalation path in the system.
- The protocol indirection makes the substrate swappable and testable (a fake backend for unit tests).

### Negative / Trade-offs
- MicroVMs cost more memory (per-VM guest kernel for Kata/Firecracker) and add operational surface
  (KVM dependency, TAP networking, kernel/rootfs management). Density drops for the sandbox tier.
- Requires `/dev/kvm`; nested virtualization must be available wherever the engine runs (bare metal or
  a nested-virt-enabled VM — not a plain LXC container).
- A migration period where both backends coexist behind the protocol.

### Neutral
- First-party service deployment is unchanged (still containers).

## Acceptance criteria

- A `SandboxProtocol` exists and the Docker backend is one implementation behind it (SPEC-190).
- No code path mounts the host Docker socket into a sandbox running untrusted code.
- At least one hardware-VM backend (Kata or Firecracker) passes the sandbox conformance/escape tests
  defined in SPEC-190.

## Open questions

1. Default backend for self-hosted (Agent Conductor) vs enterprise (Stronghold) deployments?
2. Is rootless-container an acceptable *fallback* where KVM is unavailable, or do we hard-fail closed?
3. Does the sandbox become a capability provider under SPEC-184 (so isolation level is a declared
   capability slot)?

## Source references

- `packages/maistro-core/src/maistro/tools/sandbox/docker.py` — current Docker sandbox.
- ADR-019 (canonical source split), ADR-038 (reliability taxonomy).
- SPEC-190 — pluggable sandbox substrate (the design implementing this decision).

## Out of scope

- The concrete protocol shape, backend selection, and phased migration — see SPEC-190.
- Supply-chain hardening of the *images* (distroless/Chainguard) — separate track.
