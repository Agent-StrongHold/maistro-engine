# Maistro Web Installer Delivery Plan

**Status:** Proposed implementation plan  
**Decision:** ADR-099  
**Specification:** SPEC-209  
**Rule:** Cloudflare resolves and signs declarative intent; target bootstrap owns all executable behavior.

## Product Goal

A user visits `install.maistro.dev`, selects a deployment target and desired Maistro capabilities,
reviews the resolved security/resource plan, then receives a copyable install command. The command
downloads a stable audited bootstrap and references a signed, expiring, secret-free manifest.

## Wizard Sections

1. Release channel and version.
2. Deployment target: Windows, macOS, Linux, Proxmox, VMware, Fly.io, or custom.
3. Product surface: headless, TUI-only, web UI, or full.
4. Model gateway: install LiteLLM, connect existing, direct provider, or configure later.
5. Observability: none, install Langfuse, install Phoenix, or connect OTEL.
6. Optional capabilities: crypto, Home Assistant, browser, Canvas, Turing, RSI/Evolve, notifications.
7. Exposure, sizing, backups, updates, and diagnostics.
8. Review, compatibility result, local setup requirements, and final command.

## Phase 1: Trustworthy Resolver Core

- [ ] Define manifest v2 Pydantic/JSON Schema without executable fields.
- [ ] Define the signed compatibility catalog schema.
- [ ] Implement one resolver library shared by Worker and bootstrap.
- [ ] Encode target support states: Available, Preview, Planned, and Unavailable.
- [ ] Add golden vectors and property tests for all compatibility rules.
- [ ] Define offline release root and rotating online plan-key certificate format.

Exit gate: arbitrary wizard input can produce only a valid inert manifest or a structured rejection.

## Phase 2: Stable Bootstrap

- [ ] Build small Unix and Windows bootstraps with embedded offline root key.
- [ ] Verify manifest/catalog signatures, expiry, target, release, and artifact digests.
- [ ] Implement dry-run preview, local confirmation, durable action journal, resume, rollback, status,
  and uninstall.
- [ ] Implement fixed fake recipes and prove Cloudflare cannot inject executable behavior.
- [ ] Add inspect-first and one-line command parity tests.

Exit gate: bootstrap safely applies a fake signed plan and rejects every tampering case.

## Phase 3: Cloudflare Wizard

- [ ] Build static wizard application with strict CSP and no third-party scripts.
- [ ] Add D1-backed secret-free draft sessions and immutable expiring plans.
- [ ] Add catalog, session, resolve, finalize, manifest, and command endpoints.
- [ ] Store immutable release artifacts/catalogs in R2 or an equivalent signed release store.
- [ ] Add rate limits, CSRF protection, request limits, redacted logs, and analytics exclusions.
- [ ] Display exact manifest, compatibility reasoning, resource estimates, and local-secret steps.

Exit gate: Worker, browser, and bootstrap resolve every golden vector identically.

## Phase 4: Real Target Recipes

- [ ] Linux Ubuntu VM guest bootstrap and conformance.
- [ ] Proxmox Ubuntu VM provisioner that passes a narrowed child manifest.
- [ ] Windows/macOS Docker Desktop + desktop broker + Compose bundle.
- [ ] VMware documented/manual preview, then helper after conformance.
- [ ] Keep Fly.io Planned until a secure worker provider passes conformance.

Exit gate: each Available target passes a clean-machine install, resume, upgrade, rollback, and
uninstall test.

## Phase 5: Deployment Components

- [ ] Product surfaces: headless, TUI-only, web UI, full.
- [ ] LiteLLM install/connect/configure-later modes.
- [ ] Langfuse, Phoenix, and OTEL modes.
- [ ] Local onboarding for provider credentials and external endpoints.
- [ ] Optional component recipes for Home Assistant, browser, Canvas, Turing, and RSI/Evolve.
- [ ] Crypto remains disabled until a separate local risk and identity ceremony completes.

Exit gate: every selectable component has a fixed signed recipe, compatibility rules, health check,
rollback, uninstall, and honest implementation status.

## Phase 6: Launch Gates

- [ ] Offline-signed immutable release catalog and artifacts.
- [ ] Worker compromise and artifact substitution simulations.
- [ ] No-secret scans across manifests, URLs, commands, logs, analytics, and support bundles.
- [ ] Full clean-environment matrix for every Available target.
- [ ] Accessibility, browser, mobile, and five-minute wizard UX testing.
- [ ] Public limitations and target-status page generated from the compatibility catalog.

Exit gate: the website cannot advertise or emit an install command for a target/feature combination
that has not passed its required conformance suite.

