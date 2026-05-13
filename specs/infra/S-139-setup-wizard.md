---
id: S-139
title: "Setup wizard — browser-first install ceremony, CLI fallback, shares Console codebase"
domain: infra
status: draft
priority: P1
effort: ""
created: 2026-04-25
completed: ""
owner: conductor
commits: []
supersedes: ""
---

# S-139: Setup Wizard

## Acceptance Criteria

- [ ] Default-everything wizard run completes in <5 minutes browser-first on a fresh Linux laptop with Tailscale already installed (and <10 min on a fresh machine including substrate install)
- [ ] All 12 steps render correctly on Chromium, Firefox, Safari (desktop + mobile-responsive)
- [ ] Step 4 (Create user one) is structurally required — form does not advance without a name; verified by browser automation
- [ ] Step 11 smoke tests run live and display real pass/fail; failures block wizard completion with clear remediation steps
- [ ] Step 11 smoke test failure: conductor enters `SETUP_INCOMPLETE` mode (localhost-only); a `SMOKE_TEST_FAILED` dashboard banner names the failing test with remediation steps; operator can re-run via `maistro setup --retry-smoke-tests` without restarting the wizard; non-localhost connections enabled only after all five smoke tests pass
- [ ] Wizard state persists across browser close + reopen + conductor crash
- [ ] CLI fallback (`--cli`) walks the same logical flow with a TUI presenter; verified on a no-display VM
- [ ] Headless install: prints URL + token + ssh-tunnel instructions when no graphical session detected
- [ ] Sovereignty configuration: localhost substrate + local-CA + local model + skip crypto produces a working conductor with zero outbound HTTP verifiable via tcpdump
- [ ] OAuth flows (Tailscale, NetBird, Groq, OpenRouter) complete in-browser without leaving the Console
- [ ] Hardware-wallet path (Ledger / Trezor) connected at Step 2 completes without falling back to software seed
- [ ] After wizard completion, browser auto-redirects to the substrate URL (no manual navigation required)
- [ ] Re-running `maistro setup` on a configured conductor offers reconfigure (specific steps) or full reset (admin-signed)
- [ ] On Windows: signed `.msi` install + wizard sequence completes without SmartScreen warnings
- [ ] On macOS: signed `.pkg` install (S-147) and `curl install.sh` both produce identical wizard experiences

See `blakematthews-dev/project_maistro` specs/infra/S-139-setup-wizard.md for full spec.
