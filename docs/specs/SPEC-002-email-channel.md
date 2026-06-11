---
id: SPEC-002
title: "Email channel — conductor@emeraldfam.org"
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-03-23
substrate:
  - maistro-engine#ADR-028
implements: []
related: []
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests: []
layer: Connectivity
owners:
  - '@BlakeMatthews-dev'
history:
  - status: Proposed
    date: 2026-03-23
---

# SPEC-002: Email Channel

See `blakematthews-dev/project_maistro` specs/channels/S-103-email-channel.md for full spec.

## Acceptance Criteria

**Inbound identity & anti-spoofing**
- [ ] Emails to the bare `conductor@emeraldfam.org` address are silently dropped
- [ ] Each approved sender has a unique `{code}.conductor@emeraldfam.org` address stored in the allowlist table
- [ ] Emails failing SPF, DKIM, or DMARC alignment are rejected before allowlist check
- [ ] Allowlist check validates the `{code}` prefix, not the `From:` header alone
- [ ] Rotating a sender's code does not affect any other sender

**Bouncer + injection defense**
- [ ] Subject line passes through Bouncer before task creation
- [ ] Plain-text body (HTML stripped) passes through Bouncer before task creation
- [ ] Each quoted reply block is extracted and scanned separately by the Bouncer
- [ ] A Bouncer hit drops the email silently and logs to the Security dashboard tab
- [ ] All attachments pass through `warden.file_scan()` (SPEC-001) before content enters any agent context
- [ ] Files failing magic-bytes check are hard-blocked (`FILE_INTEGRITY_VIOLATION`)
- [ ] Files triggering zip-bomb detection are hard-blocked (`ZIP_BOMB_DETECTED`)

**Dashboard queue + 2FA**
- [ ] `PRIVILEGED` tasks are held in the Dashboard Approvals queue
- [ ] The 2FA channel must never match the request channel — enforced at `EmailSender` registration and task dispatch
- [ ] Push timeout (15 min) leaves the task in the Dashboard queue — not auto-dropped

**Outbound**
- [ ] SMTP/transactional API credentials fetched via `secrets.use()` — no plaintext in env or config
- [ ] P0 infrastructure alert emails sent within 60 seconds of event

**Rate limiting**
- [ ] Per-sender cap: max 20 inbound emails per hour; excess dropped and logged
- [ ] Global inbound cap: max 100 emails per day across all senders
