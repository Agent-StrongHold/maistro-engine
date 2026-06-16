---
id: ADR-098
title: Secure default desktop install - containerized Maistro with host sandbox broker
repo: maistro-engine
kind: adr
status: Accepted
created: 2026-06-12
substrate:
  - maistro-engine#ADR-093
  - maistro-engine#ADR-097
implements: []
related:
  - maistro-engine#SPEC-180
  - maistro-engine#SPEC-190
  - maistro-engine#SPEC-208
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

# ADR-098: Secure Default Desktop Install

## Context

Windows and macOS users expect a Docker-based installation, but running the Maistro control plane
as native host processes gives a compromised service the user's full host permissions. Giving a
Maistro container the host Docker socket or direct `sbx` authority is worse: either grants a large,
general-purpose host control surface.

Docker Sandboxes provides hardware-VM-isolated execution for untrusted builders. The missing boundary
is a safe way for a trusted, containerized Maistro control plane to request sandbox lifecycle
operations without receiving the host Docker socket, arbitrary host filesystem access, or general
Docker authority.

## Decision

The official simple Windows and macOS installation target is:

```text
Windows or macOS host
├── Docker Desktop and Docker Sandboxes
├── signed Maistro Sandbox Broker
│   └── narrow, authenticated host authority for sandbox lifecycle
├── Maistro control-plane containers
│   ├── API and UI
│   ├── orchestration and durable state
│   └── sandbox protocol client
└── Docker Sandbox microVMs
    └── builders, RSI/Evolve candidates, and executable benchmarks
```

1. The complete Maistro application runs in trusted Linux containers. Native host code is limited to
   the signed installer/updater and the Maistro Sandbox Broker.
2. The broker is the only Maistro component allowed to invoke `docker sandbox`/`sbx`, access
   explicitly registered source paths, or manage sandbox lifecycle.
3. The broker exposes a versioned, narrow capability API to the trusted control-plane container. It
   is not a Docker API proxy and does not accept arbitrary Docker commands, arbitrary `sbx` flags,
   arbitrary host paths, host mounts, or runtime socket requests.
4. The Maistro containers never receive the host Docker socket, Docker Desktop credentials, broker
   host key, or unrestricted host filesystem mounts.
5. Broker transport is mutually authenticated and limited to the local Docker Desktop/control-plane
   path. If the installer cannot enforce transport authentication and local reachability, it fails
   closed.
6. Projects are registered through a host-local, user-mediated action. Runtime requests reference an
   opaque project ID, never a host path or raw repository credential.
7. The broker creates a private sanitized staging repository from an approved pinned base. Docker
   Sandboxes clone only that staging repository. Before candidate code executes, the broker verifies
   disabled push URLs, absent credentials, no live-host checkout mount, and no host runtime socket.
8. Native Windows/macOS Maistro and WSL-based Maistro are custom/development paths, not official
   secure defaults. An existing user-managed VM may be supported later as a custom deployment.
9. Failure or absence of Docker Sandboxes disables untrusted execution. The installer does not
   silently fall back to a shared-kernel container or host subprocess.

## Trust Boundaries

| Component | Trust level | Authority |
|-----------|-------------|-----------|
| Host installer/updater | Host-trusted | Install, update, remove broker and compose bundle |
| Maistro Sandbox Broker | Host-trusted, minimal | Registered projects and owned Docker Sandboxes only |
| Maistro control-plane containers | Trusted application | Request bounded broker capabilities |
| Builder sandbox | Untrusted | Work only inside its microVM and assigned project clone |
| Candidate/generated code | Hostile by default | No broker, control-plane, host, or publication authority |

Compromise of the control-plane container may consume broker-granted sandbox resources and access
registered project material, but must not become general host or Docker authority. Compromise of the
broker is a host compromise; therefore the broker remains small, signed, auditable, and free of model
execution, plugins, arbitrary shell evaluation, and business logic.

## Consequences

### Positive

- Desktop users get the familiar Docker Compose installation model.
- Maistro services run in Linux containers instead of as native Windows/macOS processes.
- Untrusted code runs behind Docker Sandbox microVM boundaries.
- The host authority is narrow enough to audit and test independently.
- The desktop and Linux installer paths converge on the same sandbox protocol and conformance suite.

### Negative / Trade-offs

- The host broker is security-critical and must be packaged for Windows and macOS.
- Docker Desktop and Docker Sandboxes become default desktop dependencies.
- Local transport differs by platform and must be hardened by the installer.
- Broker API compatibility must be maintained across independent broker and container updates.
- Docker Sandboxes product changes can require broker adapter updates.

## Current Implementation Status

This decision is accepted, but the broker, desktop installer, Docker Sandboxes adapter, and live
conformance tests are not implemented. Until SPEC-208 passes, the desktop secure default is a target
architecture, not a working production claim.

## Acceptance Criteria

- The signed broker can be installed, upgraded, rolled back, and removed without exposing the Docker
  socket to Maistro containers.
- The control plane can perform the complete `SandboxProtocol` lifecycle through the broker.
- The broker rejects arbitrary host paths, mounts, Docker commands, runtime sockets, templates,
  credentials, and unsupported `sbx` flags.
- A compromised-control-plane simulation cannot use the broker to read unregistered host files,
  manage non-Maistro sandboxes, access Docker generally, or exceed broker policy ceilings.
- Builder conformance proves no live-host checkout, no push capability, no inherited credentials, no
  host socket, default-deny execution networking, bounded resources, durable replay, and teardown.
- Unsupported Docker Desktop/Docker Sandboxes configurations fail before untrusted execution is
  enabled.

## References

- [Docker Sandboxes architecture](https://docs.docker.com/ai/sandboxes/architecture/)
- [Docker Sandboxes isolation](https://docs.docker.com/ai/sandboxes/security/isolation/)
- [Docker Sandboxes usage and clone mode](https://docs.docker.com/ai/sandboxes/usage/)

