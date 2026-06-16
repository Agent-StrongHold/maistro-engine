---
id: SPEC-208
title: Desktop Docker Sandboxes broker
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-06-12
substrate:
  - maistro-engine#ADR-093
  - maistro-engine#ADR-098
implements:
  - maistro-engine#ADR-098
related:
  - maistro-engine#SPEC-011
  - maistro-engine#SPEC-012
  - maistro-engine#SPEC-190
  - maistro-engine#SPEC-207
contracts:
  - boundary
  - behavioral
tests: []
layer: Orchestration
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-208: Desktop Docker Sandboxes Broker

## Objective

Implement the smallest host-resident authority that lets the containerized Maistro control plane use
Docker Sandboxes on Windows and macOS without receiving the host Docker socket, host filesystem
paths, Docker credentials, or arbitrary host command execution.

## Architecture

```text
Host-local user action
    │ registers a project path or approved remote
    ▼
Maistro Sandbox Broker
    ├── project registry: opaque project IDs -> approved source descriptors
    ├── private staging repositories
    ├── policy and ownership database
    ├── append-only audit log
    └── Docker Sandboxes adapter
            │
            ▼
      Docker Sandbox microVM

Maistro control-plane containers
    │ authenticated bounded requests
    └──────────────────────────────► broker
```

The broker is a separate native executable/service. It contains no model provider, agent loop,
plugin runtime, arbitrary shell endpoint, general Docker API, or application database.

## Deployment

### Desktop installer

The Windows/macOS installer:

1. detects Docker Desktop and Docker Sandboxes;
2. when missing, offers an explicit user-approved install through the platform's official package
   channel, handles required elevation/restart, and resumes from durable installer state; it never
   installs Docker Desktop silently;
3. requires the user to complete any required Docker authentication through Docker's own UI/CLI;
4. verifies a supported Docker Desktop and Docker Sandboxes version;
5. installs a signed, version-pinned broker binary as a per-user service where possible;
6. creates a broker host identity and a separate scoped client identity for this Maistro install;
7. configures a local-only broker transport reachable from the Maistro control-plane network;
8. installs the signed/pinned Maistro Compose bundle without mounting the host Docker socket;
9. mounts only the scoped broker client identity and normal Maistro data volumes into the trusted
   orchestrator container;
10. runs broker and sandbox conformance before enabling Builders, RSI/Evolve, or executable
   benchmarks;
11. records the exact Docker Desktop, Docker Sandboxes, broker, image, and Maistro versions.

The installer fails closed if it cannot enforce authenticated local transport or if Docker Sandboxes
conformance fails.

### Transport

- Protocol: versioned HTTPS/JSON for v1, with mutually authenticated TLS.
- Reachability: only the local Docker Desktop/control-plane path. The installer configures the
  narrowest available host bind and firewall rule for the platform.
- Authentication: broker-owned CA or equivalent local trust root; one scoped client identity per
  Maistro installation.
- Authorization: every request is bound to the authenticated installation ID and broker policy.
- Rotation: client identities and broker host identity rotate independently without losing campaign
  state.
- No unauthenticated health, metrics, discovery, or debug endpoint.
- The broker refuses startup if permissions on identities, policy, registry, or audit state are too
  broad.

If a later platform transport such as a safely bridged named pipe or Unix socket provides a smaller
surface, it may replace HTTPS without changing the API or authorization semantics.

### Broker implementation constraints

- Run as the installing desktop user, not as administrator/root. Elevation is limited to explicit
  installer actions such as service or firewall setup.
- Ship as a signed, dependency-minimal native executable with no plugin loader, embedded scripting
  runtime, dynamic model code, or general extension interface.
- Invoke Docker Sandboxes only through exact argv arrays for allowlisted subcommands. Never invoke a
  host shell or concatenate user-controlled command strings.
- Use an allowlisted child-process environment and broker-owned working directories.
- Treat Docker Desktop authentication as host-managed state used indirectly by approved `sbx`
  operations; never read, return, mount, or copy raw Docker credentials.
- Refuse startup or enter a no-execution state when the broker binary, configuration, policy, client
  registry, or sandbox adapter version is unverifiable.

## User Flow

1. User launches the Maistro desktop installer.
2. Installer verifies or offers to install Docker Desktop, then waits for Docker authentication and
   Docker Sandboxes readiness.
3. Installer installs the broker, scoped identity, and containerized Maistro bundle.
4. Installer runs negative broker tests and a disposable Docker Sandbox conformance run.
5. User registers a repository through the host-local broker UI/CLI and receives a Maistro-visible
   project ID.
6. Maistro starts a builder against that project ID; the broker stages the pinned source and creates
   the isolated Docker Sandbox.
7. Maistro exports a patch and evidence through the broker. Publication remains a separate external
   approval path.

## Project Registration and Staging

Project registration is a host-local, user-mediated operation and is not available to the
container-facing runtime API.

Supported registration inputs:

- an explicitly selected local Git repository;
- an explicitly approved remote Git URL fetched by the broker;
- a future signed source bundle.

Registration produces an opaque `project_id` and stores:

- canonical source identity;
- allowed base refs;
- current approved pinned commit;
- whether submodules and Git LFS are permitted;
- source allowlist and credential policy;
- maximum project size and staging retention;
- user-visible display name.

Runtime requests contain `project_id`, pinned commit, and accepted patch digest only. They never
contain a host path, arbitrary remote URL, raw credential, or Git configuration.

For each workspace, the broker:

1. resolves the approved pinned commit;
2. creates a fresh broker-owned staging repository;
3. materializes tracked content only unless the user explicitly approved a signed source bundle;
4. applies the accepted cumulative patch after verifying its digest and protected-path policy;
5. removes credential helpers, source credentials, unsafe Git protocols, and original push
   authority;
6. invokes Docker Sandboxes clone mode against the staging repository;
7. hardens and verifies the sandbox Git configuration before returning the sandbox handle;
8. removes staging material according to retention policy after replay/export requirements are met.

## Broker Runtime API

All request and response bodies carry `api_version`, `request_id`, `installation_id`, and audit
correlation ID. Mutating requests require an idempotency key.

### Capabilities

`GET /v1/capabilities`

Returns broker version, compatible protocol versions, Docker Sandboxes availability, supported
resource/network controls, and hard policy ceilings. It never returns credentials, host paths, or
general Docker information.

### Create

`POST /v1/sandboxes`

Accepted fields:

- opaque `project_id`;
- approved pinned commit and accepted patch digest;
- allowlisted builder template/profile ID;
- phase (`materialize` or `execute`);
- requested CPU, memory, disk, process, wall-time, and lifetime limits;
- requested network policy by allowlisted policy ID;
- campaign/session ownership metadata.

The broker clamps requests to policy ceilings, creates and verifies the sandbox, then returns an
opaque broker sandbox ID and actual capabilities. It never returns a Docker object ID that grants
additional authority.

### Inspect and Lifecycle

- `GET /v1/sandboxes/{id}`
- `POST /v1/sandboxes/{id}/stop`
- `POST /v1/sandboxes/{id}/resume`
- `DELETE /v1/sandboxes/{id}`

The authenticated installation may manage only its own broker-created sandboxes. Delete is
idempotent. A broker orphan sweeper destroys expired sandboxes and records every cleanup decision.

### Execute and Files

- `POST /v1/sandboxes/{id}/exec`
- `PUT /v1/sandboxes/{id}/files/{workspace-relative-path}`
- `GET /v1/sandboxes/{id}/files/{workspace-relative-path}`

Execution accepts an argv array, working directory inside the assigned workspace, bounded stdin,
timeout, and output limits. It executes only inside the owned sandbox. The API never evaluates a
host shell string.

File operations are restricted to normalized workspace and typed artifact roots. Path traversal,
absolute host paths, links escaping the workspace, devices, sockets, and unsupported file types are
rejected.

### Artifact Export

`POST /v1/sandboxes/{id}/exports`

Exports only allowlisted typed artifacts:

- Git patch against the approved pinned base plus accepted patch;
- test and benchmark reports;
- bounded logs;
- declared build artifacts;
- provenance and sandbox evidence.

The broker validates size, type, path, and digest before returning an artifact reference or stream.
It never exports credentials, `.git` credential state, sockets, devices, or arbitrary guest paths.

## Explicitly Forbidden API Surface

The broker does not provide:

- arbitrary Docker or `sbx` command execution;
- arbitrary host command execution;
- Docker socket or runtime socket forwarding;
- host bind mounts or arbitrary host paths;
- arbitrary image/template selection;
- arbitrary remote repository URLs at runtime;
- raw Git credentials, credential-helper access, or push authority;
- privileged sandbox flags;
- arbitrary port forwarding;
- requests from candidate-controlled sandboxes;
- publication, push, PR, merge, or promotion operations.

## Lifecycle and Recovery

- The control plane stores durable campaign state, pinned commit, accepted cumulative patch, and
  evidence outside candidate sandboxes.
- A sandbox may be stopped/resumed for interactive continuity, but correctness never depends on
  mutable guest state.
- After broker or host restart, owned sandboxes are reconciled against durable broker state.
- Missing, corrupt, or unverifiable sandboxes are destroyed and reconstructed from the sanitized
  staging repository.
- Every sandbox has a hard lifetime. The orphan sweeper fails closed and removes expired resources.
- Broker upgrades drain or preserve compatible sandboxes; incompatible sandboxes are replayed.

## Network Phases

- `materialize`: temporary allowlisted egress for approved source/dependency acquisition.
- `execute`: default-deny egress; no access to broker, control plane, host gateway, metadata services,
  Docker APIs, or local network.
- Phase transition creates a fresh execution sandbox or proves equivalent separation through the
  conformance suite. Network policy cannot be widened by candidate-controlled code.

## Audit and Evidence

The broker writes an append-only local audit record for:

- project registration and revocation;
- client identity issuance, rotation, and revocation;
- every sandbox create, lifecycle, exec, file, and export request;
- policy decision and actual clamped limits;
- Docker Sandboxes version and actual sandbox evidence;
- cleanup, recovery, and conformance results.

Logs redact secrets and do not store unrestricted file contents or model prompts. Audit records have
bounded retention and tamper-evident chaining or signing before the desktop path is called
production-ready.

## Threat Model

### Must resist

- hostile generated code inside a Docker Sandbox;
- a sandbox attempting to reach the broker, control plane, host, Docker socket, or local network;
- a compromised Maistro control-plane container attempting to turn the broker into general host or
  Docker authority;
- path traversal, symlink escape, command/flag injection, confused-deputy project selection, replay,
  request smuggling, resource exhaustion, and orphan accumulation;
- stolen/replayed broker client credentials after revocation;
- sandbox Git attempts to push or recover source credentials.

### Residual trust

- Docker Desktop, Docker Sandboxes, the host OS, and the hypervisor remain trusted dependencies.
- The broker is host-trusted. A broker implementation compromise is a host compromise.
- The user who installs Maistro and registers projects is trusted as the desktop administrator.
- Denial of service against the user's own desktop cannot be eliminated, but resource ceilings and
  cleanup must bound it.

## Conformance and Acceptance Tests

### Broker boundary

- A control-plane client cannot submit host paths, mounts, Docker commands, arbitrary `sbx` flags,
  unregistered projects, unapproved templates, or over-limit resources.
- One installation identity cannot inspect or manage another installation's sandboxes.
- Revoked and expired client identities fail closed.
- Malformed, repeated, reordered, oversized, and concurrent requests remain bounded and auditable.

### Sandbox boundary

- Sandbox cannot read a host marker, staging repository after handoff, broker state, or another
  sandbox.
- Sandbox cannot reach Docker/runtime sockets, broker endpoint, host gateway, control plane, cloud
  metadata, or non-allowlisted network destinations.
- Sandbox Git has no usable push URL, credentials, credential helper, or unsafe protocol.
- Resource, output, lifetime, and artifact-export limits are enforced.
- Stop/resume and pinned-base-plus-patch replay produce equivalent verified workspaces.
- Teardown and orphan cleanup remove all owned sandbox resources.

### Installer and upgrade

- Clean Windows and macOS installs pass conformance without a Docker socket mount.
- Upgrade, rollback, credential rotation, broker crash, Docker Desktop restart, and host reboot
  preserve or safely replay durable work.
- Unsupported Docker Desktop or Docker Sandboxes versions fail before untrusted execution is enabled.

## Initial Implementation Slices

1. Fake broker transport and contract tests against `SandboxProtocol`.
2. Minimal signed-development broker with capabilities, create, inspect, exec, files, export, and
   destroy.
3. Sanitized staging repository and project registration CLI/UI.
4. Docker Sandboxes adapter and live conformance harness.
5. Desktop installer, identity rotation, audit chain, recovery, stop/resume, and upgrade tests.

No slice is production-ready until the corresponding negative boundary tests pass.
