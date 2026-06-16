---
id: SPEC-209
title: Cloudflare web configurator and signed installer manifest v2
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-06-12
substrate:
  - maistro-engine#ADR-099
implements:
  - maistro-engine#ADR-099
related:
  - maistro-engine#SPEC-180
  - maistro-engine#SPEC-184
  - maistro-engine#SPEC-207
  - maistro-engine#SPEC-208
contracts:
  - boundary
  - behavioral
tests: []
layer: Orchestration
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-209: Cloudflare Web Configurator and Installer Manifest v2

## Goal

Provide a public web wizard that lets an operator select a supported deployment and feature set, then
produces a copyable bootstrap command backed by a signed, reproducible, secret-free install manifest.

## System Architecture

```text
Cloudflare Worker application
├── static wizard assets
├── signed compatibility catalog API
├── session/plan resolver API
├── short-lived secret-free plan storage
└── signed manifest endpoint

Offline release pipeline
├── signed release catalog
├── signed bootstrap binaries/scripts
├── signed component bundles
└── fixed recipe definitions

Target machine
└── stable bootstrap
    ├── verifies manifest and release signatures
    ├── runs target preflight
    ├── previews exact fixed actions
    ├── obtains local confirmation
    ├── applies/resumes/rolls back
    └── launches local secret/configuration onboarding
```

Recommended Cloudflare primitives:

- Worker Static Assets for the wizard application.
- Worker API routes for catalog, validation, and plan creation.
- D1 for short-lived wizard sessions and plan records.
- R2 for immutable signed release catalogs, bootstraps, and component bundles.
- Worker secrets only for the rotating online plan-signing key and service credentials.
- Rate limiting and abuse controls on write endpoints.

The offline release signing key never exists in Cloudflare.

The Worker-hosted one-line bootstrap is a convenience path that trusts the Worker/custom-domain TLS
delivery for the first executable. It can verify every subsequent artifact but cannot verify itself
before execution. A high-assurance path must use an immutable signed bootstrap package and an
independently distributed trust anchor or platform code-signing verification.

## Wizard Flow

### 1. Release

- Stable, beta, or explicitly pinned release.
- Wizard displays release date, support status, artifact signatures, and compatibility-catalog
  version.

### 2. Deployment target

- Windows
- macOS
- Linux
- Proxmox
- VMware
- Fly.io
- Other/custom

The target selection determines the installation envelope and preflight. It does not let users pick
a weaker sandbox silently.

### 3. Product surface

- `headless`: API/background services, no interactive UI.
- `tui-only`: terminal UI and CLI, no web UI.
- `web-ui`: API plus web UI, no TUI package.
- `full`: TUI, API, and web UI.

Every production surface still includes the required sandbox worker and persistence.

### 4. Model gateway

- Install managed-local LiteLLM.
- Connect to an existing LiteLLM endpoint.
- Direct provider configuration, when supported.
- No model gateway yet, producing a setup-incomplete install that cannot run agents.

The manifest records only the selected mode. Existing endpoint URLs and all provider credentials are
entered locally after installation.

### 5. Observability

- None/minimal local logs.
- Install Langfuse.
- Install Phoenix.
- Connect to an existing OpenTelemetry collector.

The manifest records component and connection intent. Endpoint values and credentials are entered
locally. The resolver rejects observability choices unsupported by the selected target/resources.

### 6. Optional capability groups

- Crypto: disabled by default; identity-only or wallet/transaction capabilities require a separate
  local risk ceremony.
- Home Assistant: connect after install; Worker never receives HA URL/token.
- Approval/notification providers.
- Browser automation.
- Canvas.
- Turing/autonoetic extensions.
- RSI/Evolve autonomous campaigns.
- Additional product/plugin selections as the signed catalog grows.

Selections enable fixed install components only. High-risk permissions remain disabled until local
post-install policy and credential setup is complete.

### 7. Exposure and operations

- Localhost/private only by default.
- Optional approved ingress/network substrate.
- Backup and update policy.
- Resource sizing preset.
- Telemetry/diagnostic consent.

### 8. Review and command

The review page shows:

- selected target and resolved install envelope;
- installed and externally connected components;
- required manual/local-secret steps;
- security posture and unavailable capabilities;
- estimated CPU, memory, disk, ports, and external accounts;
- exact manifest JSON;
- recommended inspect-first command;
- optional short one-line command;
- plan expiry and reproducibility identifier.

## Compatibility Catalog

The signed catalog is data, not executable code. It defines:

- available targets and support state;
- architecture and minimum-version requirements;
- allowed product surfaces;
- component IDs and dependency/conflict rules;
- resource minimums;
- fixed recipe IDs implemented by bootstrap;
- required preflight checks;
- sandbox/isolation guarantees;
- post-install local setup requirements;
- release artifact digests and signatures.

The UI uses the catalog for immediate feedback. The Worker resolver and bootstrap independently
validate against the same signed catalog.

### Initial compatibility decisions

| Target | Initial status | Resolution |
|--------|----------------|------------|
| Windows | Planned until SPEC-208 passes | Docker Desktop + broker + containerized Maistro |
| macOS | Planned until SPEC-208 passes | Docker Desktop + broker + containerized Maistro |
| Linux | Planned until SPEC-207 passes | Ubuntu Server VM guest install |
| Proxmox | Planned until helper passes | Provision Ubuntu VM + common guest install |
| VMware | Preview after documented conformance | Provision Ubuntu VM with nested virtualization + common guest install |
| Fly.io | Planned | No command until a conforming secure worker provider exists |
| Other/custom | Planned/manual | No generated executable plan unless a signed target recipe exists |

Fly.io may eventually use Fly Machines as an explicit sandbox provider. It does not pretend to run
the Docker Sandboxes default without proof.

## Manifest v2

The manifest is canonical JSON signed by an online plan key certified by the offline release trust
root. It contains no secrets.

```json
{
  "kind": "maistro_install_manifest",
  "schema_version": "2",
  "plan_id": "opaque-id",
  "created_at": "2026-06-12T00:00:00Z",
  "expires_at": "2026-06-15T00:00:00Z",
  "catalog": {
    "release": "v1.0.0",
    "channel": "stable",
    "digest": "sha256:..."
  },
  "target": {
    "id": "proxmox",
    "architecture": "x86_64",
    "recipe": "proxmox-ubuntu-vm-sbx-v1"
  },
  "surface": "full",
  "components": [
    "maistro-core",
    "maistro-server",
    "maistro-tui",
    "maistro-web",
    "litellm-managed",
    "phoenix-managed",
    "rsi-evolve"
  ],
  "connections": {
    "llm_gateway": "managed",
    "observability": "managed",
    "home_assistant": "configure-locally"
  },
  "capabilities": {
    "crypto": "disabled",
    "autonomous_builders": "enabled-after-conformance"
  },
  "operations": {
    "exposure": "private",
    "updates": "manual",
    "backup": "prompt"
  },
  "required_local_setup": [
    "provider_credentials",
    "admin_identity"
  ]
}
```

Forbidden manifest fields and values:

- raw shell/PowerShell/argv;
- arbitrary URLs or artifact locations;
- arbitrary host paths, mount specifications, ports, or firewall rules;
- secrets, tokens, passwords, seed material, private keys, or private repository credentials;
- inline compose, cloud-init, Terraform, Dockerfiles, or scripts;
- unregistered recipe/component/plugin IDs;
- a requested isolation tier weaker than the target catalog requires.

## Worker API

### Catalog

- `GET /v2/catalog`
- `GET /v2/catalog/releases/{release}`

Returns signed catalog data and ETags. Catalog endpoints contain no user-specific data.

### Session

- `POST /v2/sessions`
- `GET /v2/sessions/{id}`
- `PATCH /v2/sessions/{id}`
- `DELETE /v2/sessions/{id}`

Sessions hold secret-free draft selections with a short TTL. Mutation uses CSRF protection,
rate-limiting, strict schema validation, and optimistic concurrency/version checks.

### Resolve

- `POST /v2/sessions/{id}/resolve`

Returns normalized choices, incompatibilities, warnings, resource estimates, required local setup,
and the selected fixed target recipe. It never returns executable shell generated from selections.

### Finalize

- `POST /v2/sessions/{id}/finalize`
- `GET /v2/plans/{plan_id}/manifest`
- `GET /v2/plans/{plan_id}/commands`

Finalize creates an immutable, signed, expiring plan. Commands are fixed templates containing only
the stable bootstrap location, plan ID, and optional expected bootstrap digest.

## Final Command UX

### Recommended Unix inspect-first flow

```bash
curl -fsSLo maistro-bootstrap.sh https://install.maistro.dev/bootstrap.sh
less maistro-bootstrap.sh
sh maistro-bootstrap.sh --plan PLAN_ID
```

### Optional Unix one-liner

```bash
curl -fsSL https://install.maistro.dev/bootstrap.sh | sh -s -- --plan PLAN_ID
```

The UI labels this as the convenience/TLS-trusted path, not the high-assurance path.

### High-assurance flow

The UI links an immutable bootstrap release and signature from the release origin, shows the expected
signing identity/key fingerprint from a separate trust document, and emits platform-specific
download, verify, then run instructions. The exact mechanism may use OS code signing, a bundled
verifier, or an already-installed approved signature tool.

### Windows flow

The page emits an inspect-first PowerShell download/verify/run flow and an optional short command.
The signed bootstrap executable/script and plan manifest are verified before mutation. The plan ID is
not a secret, but no credentials are placed on the command line.

### Multi-stage target flow

Proxmox and future VMware helpers may emit two stages:

1. host-side helper provisions the approved Ubuntu VM;
2. helper passes a signed child manifest to the common guest bootstrap.

The child manifest is derived from and linked to the original plan. It cannot broaden capabilities.

## Stable Bootstrap Contract

The bootstrap is a small target-specific verifier and dispatcher. It:

1. detects target OS/architecture and rejects a mismatch;
2. downloads plan manifest and signed release catalog over HTTPS;
3. verifies signature chain, canonical encoding, expiry, release compatibility, and artifact digests;
4. re-resolves the manifest against the catalog;
5. runs read-only preflight and prints a complete mutation plan;
6. requires local confirmation unless an explicit automation policy was provided locally;
7. creates durable local install state before mutation;
8. invokes fixed recipe handlers by ID;
9. supports resume, status, rollback, and uninstall;
10. runs conformance and health checks before declaring success;
11. starts local onboarding for secrets, identities, external endpoints, and high-risk capabilities.

The bootstrap never evaluates a command received from Cloudflare.

## Secret Handling

- Cloudflare never asks for or stores API keys, passwords, private endpoint credentials, crypto seed
  material, Home Assistant tokens, SSH keys, or private Git credentials.
- Existing endpoint URLs are entered locally by default because they may reveal internal topology.
- Local onboarding stores secrets only through the approved vault/keychain path.
- The manifest may declare that a secret or connection is required, but never its value.
- Install logs redact local secret input and never upload it by default.

## Persistence, Resume, and Expiry

- Draft sessions expire quickly and can be deleted by the user.
- Final plans are immutable, short-lived, and rerunnable during their TTL.
- Bootstrap stores a local normalized manifest and durable action journal so installation can resume
  after reboot, Docker Desktop setup, package-manager restart, VM provisioning, or network failure.
- After plan expiry, resume uses the locally verified manifest and pinned catalog; a fresh online plan
  is required only to change selections or release.
- Every action is idempotent or has an explicit rollback/repair handler.

## Security Requirements

- Strict CSP and no third-party script execution on the wizard page.
- No secrets or configuration in analytics, URLs, query strings, referrers, or logs.
- Server-side schema and compatibility validation; never trust disabled UI controls.
- Short request/body limits, rate limits, CSRF protection, and abuse controls.
- Signed catalog and manifests use canonical encoding and explicit key IDs.
- Online plan-signing key rotates and is certified by an offline release root.
- Bootstrap embeds/trusts only the offline root and rejects unknown online keys.
- Offline-signed catalog constrains all executable recipes, components, and artifact digests.
- Worker compromise cannot introduce arbitrary executable behavior.

## Acceptance Tests

### Resolver

- Property/fuzz tests cover every target, surface, component, provider, capability, and conflict.
- UI resolver, Worker resolver, and bootstrap resolver produce identical normalized results.
- Unsupported combinations never produce an executable command.

### Manifest boundary

- Injection strings in every wizard field remain inert data or are rejected.
- Unknown fields, IDs, recipes, URLs, commands, paths, and weaker isolation requests fail closed.
- Secret-pattern tests prove manifests, commands, Worker logs, and analytics remain secret-free.
- Tampered, expired, replay-policy-violating, or wrongly signed plans fail before mutation.

### Bootstrap

- Clean-environment tests for each Available target.
- Resume tests across every reboot/restart boundary.
- Idempotent rerun, rollback, uninstall, and failed-conformance behavior.
- Artifact substitution, catalog downgrade, Worker compromise simulation, and signature-key rotation.

### User experience

- A simple supported install takes fewer than five minutes of wizard interaction before local
  dependency installation time.
- Review page clearly distinguishes installed components, external connections, local secret steps,
  planned/unavailable capabilities, and security implications.
- Inspect-first and one-line commands resolve to the identical verified manifest and actions.
- The UI accurately distinguishes first-bootstrap delivery trust from the signature verification the
  bootstrap performs after it starts.

## Delivery Slices

1. Manifest v2 schema, compatibility catalog, resolver library, and golden vectors.
2. Stable bootstrap verifier with dry-run, action journal, resume, and fake recipes.
3. Cloudflare static wizard and secret-free session/resolve/finalize API.
4. Linux guest recipe and Proxmox helper integration.
5. Desktop broker/Compose recipe integration.
6. Component recipes for surfaces, LiteLLM, Langfuse, Phoenix, OTEL, and optional capabilities.
7. Clean-environment conformance, release signing, rollbacks, and public launch.
