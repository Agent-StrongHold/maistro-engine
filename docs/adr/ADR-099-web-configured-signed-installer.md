---
id: ADR-099
title: Web-configured installer with signed declarative manifests
repo: maistro-engine
kind: adr
status: Accepted
created: 2026-06-12
substrate:
  - maistro-engine#ADR-097
  - maistro-engine#ADR-098
implements: []
related:
  - maistro-engine#SPEC-180
  - maistro-engine#SPEC-207
  - maistro-engine#SPEC-208
  - maistro-engine#SPEC-209
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests: []
layer: Orchestration
owners:
  - '@BlakeMatthews-dev'
---

# ADR-099: Web-Configured Signed Installer

## Context

Maistro needs a friendly installer that can express deployment substrate, user interface, model
gateway, observability, integrations, and optional capabilities. The natural experience is a web
wizard that ends with a copyable install command.

Generating unique arbitrary shell scripts from web form input creates an unauditable remote-code
execution service. Putting API keys or other secrets into the wizard, generated URL, command line,
or shell history also creates an unacceptable secret-handling path.

## Decision

1. The public installer configurator is a Cloudflare Worker application serving a static web wizard
   and a resolver API.
2. The Worker resolves selections into a versioned **declarative install manifest**. It never
   generates arbitrary shell, PowerShell, Docker commands, cloud-init, or Terraform from user input.
3. The final output is a platform-appropriate command that downloads one stable, audited bootstrap
   program and passes it an opaque plan ID:

   ```bash
   curl -fsSL https://install.maistro.dev/bootstrap.sh | sh -s -- --plan PLAN_ID
   ```

   An inspect-first download/check/run command is displayed as the recommended option. Windows shows
   an equivalent signed PowerShell/bootstrap executable flow.
   The one-liner necessarily trusts HTTPS delivery of the bootstrap itself and is labeled the
   convenience path. High-assurance installs download a signed bootstrap release from the immutable
   release origin, verify it with an independently distributed trust anchor or OS signing mechanism,
   then run it with the plan ID.
4. The bootstrap downloads the manifest, verifies its signature and expiry, resolves only
   offline-signed release artifacts and recipes, displays the complete plan, obtains local consent,
   then applies fixed handlers.
5. A manifest contains selection intent and fixed recipe/component IDs only. It cannot contain raw
   commands, arbitrary download URLs, arbitrary host paths, inline scripts, credentials, or secrets.
6. Provider API keys, existing service credentials, crypto seed material, Home Assistant tokens,
   private repository credentials, and other secrets are collected locally after bootstrap through
   the installed setup flow and stored in the approved local vault/keychain.
7. The resolver uses a signed compatibility catalog. Impossible or unsafe combinations are disabled
   in the UI and rejected again by both the Worker and bootstrap.
8. Install plans are short-lived, rerunnable, non-secret records. They may be stored by opaque ID,
   but contain no user credentials or sensitive endpoint values.
9. Release artifacts and executable recipes are signed offline. Compromise of the online Worker plan
   signer must not allow arbitrary code or URLs to be executed by bootstrap.
10. The same manifest schema drives the web wizard, headless answers files, installer tests, and
    future setup UI. There is one resolver and one compatibility model.

## Deployment Target Semantics

The wizard may list targets before they are supported, but it must distinguish:

- **Available**: resolver and clean-environment conformance tests pass.
- **Preview**: manifest can be generated, but the operator must complete documented manual steps.
- **Planned**: visible for roadmap clarity; no executable command is generated.
- **Unavailable combination**: target conflicts with selected security or feature requirements.

Initial target intent:

| Target | Resolution |
|--------|------------|
| Windows | ADR-098 desktop containers + host sandbox broker |
| macOS | ADR-098 desktop containers + host sandbox broker |
| Linux | ADR-097 supported Ubuntu VM guest installer |
| Proxmox | Provision Ubuntu VM, then invoke common ADR-097 guest installer |
| VMware | Provision Ubuntu VM with nested virtualization, then invoke common guest installer; helper is preview until implemented |
| Fly.io | Planned custom deployment; no secure default command until a conforming worker provider exists |
| Other/custom | Planned or documented manual deployment; never silently weakened |

## Consequences

### Positive

- The installer feels customized without creating a remote arbitrary-script generator.
- Every install can be reproduced from a signed manifest and pinned release catalog.
- Secrets never need to pass through Cloudflare or appear in generated commands.
- Unsupported combinations fail before machine mutation.
- Web, headless, CI, and future local setup flows share one schema and resolver.

### Negative / Trade-offs

- Bootstrap and compatibility-catalog design are more work than string-building shell scripts.
- The online manifest service, signing hierarchy, expiry, and storage require operations.
- Some targets must remain visibly planned instead of producing a misleading command.
- Local post-install onboarding is still required for secrets and high-risk capabilities.

## Current Implementation Status

The v1 bootstrap planner exists, but the Cloudflare configurator, manifest v2 schema, signed catalog,
stable bootstrap, and target helpers are not implemented. This ADR defines the target behavior only.

## Acceptance Criteria

- Fuzzed wizard input cannot place a raw command, URL, path, or secret into executable bootstrap
  behavior.
- Bootstrap rejects expired, malformed, unsigned, incompatible, and unknown manifests/components.
- Worker compromise cannot redirect bootstrap to an unsigned artifact or introduce a new executable
  recipe.
- The final command contains only the stable bootstrap URL and opaque non-secret plan identifier.
- The review page states the bootstrap trust difference between convenience, inspect-first, and
  cryptographically verified high-assurance flows.
- Clean-environment tests cover every target marked Available.
- The UI and bootstrap produce the same rejection reason for every unsupported combination.
