# Agent-Framework Security Flaws Ledger

**Status:** Living document (started 2026-06-21)
**Owner:** @BlakeMatthews-dev
**Scope:** maistro-engine (Agent Conductor / homelab posture). Stronghold's multi-tenant
posture is stricter and tracked separately (ADR-019).

---

## Why this document exists

The AI-agent-framework ecosystem is being actively exploited. The same class of flaw —
**ship arbitrary code/expression execution as a feature, behind weak or no authorization, with
shared-kernel or no isolation** — has produced maximum-severity, in-the-wild RCE across Langflow,
Flowise, n8n, LangChain, and the MCP tooling, with botnets (Flodrix) and 12,000+ exposed instances
per platform. The trigger for this ledger was VentureBeat's *"7,000 Langflow servers under attack;
LangGraph, LangChain same holes"* (2026), but the pattern long predates that piece.

This ledger does three things for every serious flaw we track:

1. **Names the flaw** — the concrete CVE / disclosure and its root cause, generalized to the
   *attack class* (not just the one product's bug).
2. **States how our design changes the outcome** — which structural control (ADR/SPEC/code)
   applies, and *why* it removes or shrinks the flaw rather than papering over it.
3. **Scores the residual honestly** — upstream severity → our residual estimate, **plus an
   explicit gaps/residual-risk note**. We mark whether the control is `Implemented`, `Specified`
   (decided, partially built), or `Planned`. A specified-but-unbuilt control is *not* counted as
   mitigation in the residual score.

This is a candor exercise, not a marketing one. Where we are exposed, it says so.

### Methodology / severity scale

- **Upstream severity** is the published CVSS (v3.1 unless noted v4.0).
- **Maistro residual** is our estimate of the same attack's severity *against this engine as
  designed and implemented today*, on the same 0–10 scale, with a one-word band:
  `Eliminated` (root cause structurally absent), `Strongly reduced`, `Reduced`, `Partial`,
  `Unchanged`. The number is an engineering estimate, not a scored CVSS.
- A residual is only as good as the **implementation status** of the control it leans on.
  Specified-but-unbuilt controls are listed as defense-in-depth *direction*, not as current
  mitigation.

### How to add an entry

Copy the template at the bottom. One entry per *attack class*; list multiple CVEs under the same
class when they share a root cause. Always fill the **Residual risk / gaps** line — an entry with no
honest gap is a red flag, not a clean bill of health.

---

## Summary

| # | Attack class | Anchor CVE(s) | Upstream | Maistro residual | Primary control | Status |
|---|--------------|---------------|----------|------------------|-----------------|--------|
| 1 | Unauthenticated code/expression-exec endpoint | Langflow CVE-2025-3248 (9.8); Flowise CVE-2025-59528 (10.0); n8n CVE-2025-68613 (9.9); MCP Inspector CVE-2025-49596 (9.4) | 9.4–10.0 | ~2–3 *Strongly reduced* | No exec endpoint + sandbox (ADR-093) + auth on every boundary (ADR-068) | Mixed |
| 2 | Insecure deserialization / serialization injection | LangChain "LangGrinch" CVE-2025-68664 (9.3); CVE-2024-36480 (9.0) | 9.0–9.3 | ~2 *Strongly reduced* | No untrusted→live-object load; secrets in vault not env (ADR-072 assets, `vault.py`) | Implemented |
| 3 | Web-driven account takeover → RCE | Langflow CVE-2025-34291 (9.4 v4) | 9.4 | ~3 *Reduced* | Web-session hardening (ADR-077) + OAuth2 (ADR-059) + #1's exec absence | Specified |
| 4 | SSRF via agent tools | LangChain CVE-2023-46229 | 8.x | ~3 *Reduced* | Egress allow-list + Warden egress scan + tool sandbox (ADR-093 / SPEC-190) | Mixed |
| 5 | Indirect / zero-click prompt-injection exfiltration | EchoLeak CVE-2025-32711 (9.3) | 9.3 | ~4 *Partial* | External-content quarantine + bidirectional Warden + authority envelope (ADR-068) + egress | Mixed |
| 6 | MCP tool poisoning / rug-pull / shadowing / confused deputy | MCP ecosystem (no single CVE); CVE-2025-49596 for Inspector | n/a–9.4 | ~3 *Reduced* | Skills/MCP trust tiers + signing (ADR-083) + bidirectional Warden + Sentinel adjudication | Mixed |
| 7 | Malicious third-party code / supply chain | (class; Langflow Flodrix botnet as outcome) | up to 10.0 | ~3 *Reduced* | microVM isolation (ADR-093) + signing + SBOM + egress (ADR-072 anchor adversary) | Specified |
| 8 | Transparent credential/traffic exfil via shared config | LangSmith "AgentSmith" CVE-class (8.8) | 8.8 | ~3 *Reduced* | Per-user encrypted creds + provider-key redaction + egress allow-list | Mixed |
| 9 | Memory / learned-policy poisoning | (class; agent-memory research) | n/a | ~3 *Reduced* | Memory scopes + deconfliction immune system (ADR-074) | Specified |
| 10 | Excessive agency / over-privileged tool use | (OWASP LLM06; class) | n/a | ~3 *Reduced* | Authority envelope (ADR-068) + reversibility gates (ADR-050/051) + trust-boundary grants | Implemented |

---

## 1. Unauthenticated code / expression execution endpoint

**Anchor CVEs.** Langflow `CVE-2025-3248` (CVSS 9.8) — unauthenticated RCE: `/api/v1/validate/code`
calls Python `exec()` on user-supplied code with no auth and no sandbox; weaponized in the wild to
drop the **Flodrix** botnet, added to CISA KEV. Flowise `CVE-2025-59528` (CVSS 10.0) — the
`CustomMCP` node evaluates a user-supplied config string as JavaScript with full Node runtime
(`child_process`, `fs`); ~12–15k instances exposed. n8n `CVE-2025-68613` (CVSS 9.9) — expression
injection escapes the workflow-expression sandbox to OS command execution. MCP Inspector
`CVE-2025-49596` (CVSS 9.4) — unauthenticated command execution against the dev tool.

**Root cause (generalized).** Visual/low-code agent builders treat "run this code/expression" as a
*product feature* and expose it on a network endpoint that is (a) unauthenticated or weakly
authenticated and (b) not isolated from the host. The interpreter *is* the vulnerability.

**How our design changes the outcome.**
- **No equivalent endpoint exists.** The engine exposes no route that compiles or `exec()`s
  caller-supplied source. We verified this: the only `exec()` of model/generated code in-tree is the
  evaluation **benchmark harness** (`packages/hive-conductor/eval/benchmarks/coding.py`), an offline
  scoring path, not a network surface. Tool execution goes through a `SandboxProtocol`
  (`maistro.tools.sandbox`) whose `.exec(command)` runs **inside a sandbox container/VM**, never as
  `exec()` on the API process.
- **Sandbox isolation is a posture decision, not a default.** ADR-093 *requires* untrusted,
  model-generated code to run behind a **hardware-VM boundary (microVM)**, deprecates the
  Docker-socket-mounting sandbox, and **fails closed** if no acceptable isolation tier is present —
  with a stricter floor for unattended/autonomous runs (Tier 2 gVisor-or-better) than for supervised
  interactive use (Tier 3). Even a successful in-sandbox exec lands the attacker in a disposable
  guest, not on the host.
- **Auth on every boundary.** ADR-068 makes Sentinel the policy decision/enforcement point at every
  tool-call boundary; ADR-059/SPEC-183 add OAuth2 user auth; B2B service keys (`maistro.auth`) and
  the conductor auth middleware gate the API surface. There is no "validate" path that skips authz.

**Upstream 9.4–10.0 → Maistro residual ~2–3 (Strongly reduced).** The root-cause primitive (an
unauthenticated host-context interpreter) is structurally absent; the worst realistic outcome of a
tool that *does* run code is confinement inside a fail-closed sandbox.

**Residual risk / gaps.** ADR-093's microVM mandate is **Specified, partially implemented** —
production still has a Docker path during the SPEC-190 migration, and the strong guarantee depends on
`/dev/kvm` being available; on a Tier 3-only host, interactive execution still proceeds behind a
shared kernel (autonomous is refused). The egress/secrets hygiene *inside* the sandbox is as
load-bearing as the boundary (ADR-093 §industry-survey #3) and is tracked under SPEC-190. **Status:
Mixed.**

---

## 2. Insecure deserialization / serialization injection

**Anchor CVEs.** LangChain Core **"LangGrinch" `CVE-2025-68664`** (CVSS 9.3) — `dumps()`/`dumpd()`
fail to escape free-form dicts carrying the reserved `lc` marker key; a prompt-injected model output
can forge a "trusted LangChain object" on the way back through `load()`/`loads()`, yielding env-secret
extraction (`secrets_from_env=True` was the default), instantiation of classes in trusted namespaces,
and code execution via Jinja2 templates. LangChain `CVE-2024-36480` (CVSS 9.0) — RCE via unsafe
load. Root cause: **untrusted data is deserialized into live objects**, and secrets are sitting in
process env where a deserializer can scoop them.

**How our design changes the outcome.**
- We do **not** rehydrate untrusted/model-produced payloads into executable objects. Persistence uses
  typed stores (Pydantic/SQLAlchemy validation), not `pickle.loads`/`yaml.load`/object-graph
  deserializers on attacker-influenced input (verified: no such call on an untrusted path in-tree).
- **Secrets aren't in env-injectable reach.** ADR-072 lists provider credentials and the Conductor
  seed as top assets guarded by the **age-encrypted vault** (`vault.py`, SPEC-011) and a redaction
  layer (ADR-064) — not loose process-environment variables a deserializer can read. The exact
  `secrets_from_env`-style amplifier that made LangGrinch a *secret-exfil* bug is absent.
- Template rendering uses Jinja2's sandboxed/escaped path for any value that could carry untrusted
  content; untrusted text is quarantined as data (see entry 5), not handed to a template compiler.

**Upstream 9.0–9.3 → Maistro residual ~2 (Strongly reduced).** Both the deserialization gadget and
its secret-exfil amplifier are absent by construction.

**Residual risk / gaps.** Third-party dependencies could still introduce an unsafe loader; this is
covered transitively by the supply-chain controls in entry 7 and the `security-scan` / SCA CI gates,
not by anything specific to this class. **Status: Implemented.**

---

## 3. Web-driven account takeover → RCE

**Anchor CVE.** Langflow `CVE-2025-34291` (CVSS v4.0 9.4) — a victim merely visiting a malicious page
leads to full account takeover and RCE (CSRF/session-handling weaknesses chained into the code-exec
surface of entry 1).

**How our design changes the outcome.**
- **ADR-077 (web-session security)** specifies the session-handling hardening (cookie flags, CSRF
  defenses, session fixation/rotation) that this class abuses; **ADR-059/SPEC-183** put user auth on
  OAuth2.
- The *chain* this CVE relies on — takeover *then* a code-exec endpoint — is broken at the second
  link by entry 1: there is no host-context exec endpoint for a hijacked session to reach.

**Upstream 9.4 → Maistro residual ~3 (Reduced).** Account-takeover impact is bounded by the authority
envelope (entry 10) and the absence of a code-exec amplifier; a stolen session is still a real
incident, just not an automatic host RCE.

**Residual risk / gaps.** ADR-077 is **Specified**; the concrete web-session hardening must be
audited against the live hive-conductor frontend/auth middleware before claiming the chain is fully
broken. **Status: Specified.**

---

## 4. SSRF via agent tools

**Anchor CVE.** LangChain `CVE-2023-46229` — SSRF via sitemap/URL-loading tools reaching internal
network resources. Generalizes to any agent tool that fetches a URL the model (or injected content)
chose.

**How our design changes the outcome.**
- **Egress allow-list + bidirectional Warden.** ADR-072/073 require Warden to scan the MCP boundary in
  **both directions** and put outbound traffic behind an egress allow-list; ADR-058 adds per-peer
  egress allow-listing for federation. A tool fetch to a non-allow-listed internal address is a
  denied egress, not a silent SSRF.
- **Tool fetches run in the sandbox** (ADR-093 / SPEC-190), so even a successful internal request
  originates from a confined network namespace with deny-by-default egress, not from the host with
  LAN reach.

**Upstream ~8.x → Maistro residual ~3 (Reduced).** The "reach arbitrary internal host" primitive is
gated by allow-listed egress rather than open by default.

**Residual risk / gaps.** Egress allow-listing is **Specified in SPEC-190 and partially enforced**;
until the deny-by-default egress profile is the verified default on every sandbox tier, a
metadata-endpoint or LAN-pivot SSRF remains partially open. **Status: Mixed.**

---

## 5. Indirect / zero-click prompt-injection exfiltration

**Anchor CVE.** **EchoLeak `CVE-2025-32711`** (CVSS 9.3) — the first real-world *zero-click* prompt
injection causing concrete data exfiltration from a production LLM system (M365 Copilot). A crafted
email (hidden HTML-comment / white-on-white payload) is retrieved into Copilot's context and chains
classifier evasion + Markdown link/image auto-fetch + a CSP-allowed proxy to silently exfiltrate
anything the assistant can read. This is the **structural** agent risk, not a product bug.

**How our design changes the outcome.**
- **Untrusted content is quarantined as data.** `maistro.security.external_content` wraps every
  external source (email, webhook, web fetch, browser, upload) in explicit
  `<<<EXTERNAL_UNTRUSTED_CONTENT>>>` boundary markers with a do-not-follow notice, **NFKC-normalizes
  and strips invisible/zero-width characters** (the exact white-on-white / hidden-char trick EchoLeak
  used), and runs `detect_injection()` pattern matching. The Gate (`security/gate.py`) sanitizes and
  Warden-scans all user input before it reaches the agent, with strike-based lockout on repeat
  violations.
- **Bidirectional Warden.** ADR-072/073: Warden scans **egress** as well as ingress — "an
  exfiltration attempt leaves as much as it enters." The auto-fetch-an-image exfil channel is an
  outbound event subject to the egress allow-list.
- **Authority envelope.** ADR-068's invariant — *an injected request can never exceed the principal's
  authority* — is the structural backstop the threat model (ADR-072 adversary #2) relies on and is
  named as a property test. Injection can't grant the agent reach it didn't already have.

**Upstream 9.3 → Maistro residual ~4 (Partial).** We remove the specific delivery tricks (invisible
chars, marker confusion) and constrain the exfil channel (egress + bounded authority), but **prompt
injection is not solved by anyone** — detection is heuristic.

**Residual risk / gaps.** Warden's fast tier is pattern/heuristic + an LLM-judge escalation; a novel,
well-obfuscated indirect injection can still pass detection. The honest defense here is *containment*
(quarantine + egress + authority bound), not *detection*. Egress allow-listing being only partially
enforced (entry 4) is the load-bearing gap. **Status: Mixed.**

---

## 6. MCP tool poisoning / rug-pull / tool shadowing / confused deputy

**Anchor disclosures.** Empirical study of 1,899 MCP servers: **5.5% exhibited tool poisoning**
(malicious instructions hidden in tool descriptions/metadata). **Rug pull** — a trusted tool ships a
later malicious update to harvest env/API keys. **Tool shadowing / line jumping** — register a tool
whose name/description shadows a legitimate one so the router hands it sensitive params. **Confused
deputy / token passthrough** — an MCP server forwards a client token to a downstream API without
validating audience. First malicious MCP package observed in the wild Sept 2025; MCP Inspector
`CVE-2025-49596` (9.4) for the unauth-exec variant.

**How our design changes the outcome.**
- **Trust tiers + signing for skills/MCP.** ADR-083 (skills/MCP trust) and ADR-069/070 (code-registry
  signing + the verify/Rehearse gate) make external tools **untrusted-by-default**, signed, and
  trust-tiered — a rug-pull update is a new artifact that must re-pass the verify gate, not a silent
  swap.
- **Bidirectional Warden on tool metadata and I/O.** Tool descriptions are untrusted content scanned
  on the way in (poisoned-description detection), and tool output is scanned on the way out
  (exfil/shadowing). Sentinel adjudicates every tool call (ADR-068/073), so a shadowed tool still
  faces tier resolution + approver matrix + reversibility gate before it runs.
- **No token passthrough.** Authz is scoped per principal (ADR-068); we don't forward caller tokens
  to downstream APIs as bearer credentials — the confused-deputy primitive is absent by design.
- **microVM containment (ADR-093)** bounds what a poisoned/rug-pulled tool can reach once running.

**Upstream up to 9.4 → Maistro residual ~3 (Reduced).** Poisoning and rug-pull become detectable,
signed, gated, and confined rather than silent and host-wide.

**Residual risk / gaps.** Poisoned-description *detection* shares the heuristic ceiling of entry 5.
Signing/trust-tier enforcement (ADR-083/069/070) is **Specified, partially implemented**; until the
verify-gate is mandatory on every MCP-tool registration path, a poisoned tool can still be admitted
on an unguarded path. **Status: Mixed.**

---

## 7. Malicious third-party code / supply chain (the anchor adversary)

**Context.** This is ADR-072's **#1 adversary** ("malicious third-party code") and the *outcome* layer
of entry 1 (Flodrix botnet on compromised Langflow hosts). A bad skill, compromised MCP server, or
poisoned dependency that exfiltrates, escalates, or poisons.

**How our design changes the outcome.**
- **Structural, not behavioral** (ADR-028): defenses are enforced by substrate, never by asking the
  model to self-limit. Untrusted code runs in a **microVM** (ADR-093, fail-closed), is **signed +
  trust-tiered** (ADR-069/070/083), inventoried via **SBOM**, and constrained by **egress control**.
- **Untrusted-by-default reversibility** (ADR-050): external code/tools default to `irreversible` and
  require an explicit, signed Sentinel policy to downgrade.
- Per-task **trust-boundary permission grants** (`security/trust_boundary.py`) are time-limited
  (TTL), workspace-scoped (path-traversal-rejecting), and restrict execution to an allow-listed
  command regex (`^(python|pytest|ruff|mypy|git|npm|pip|uv)\b`) — a compromised task can't `curl|sh`.

**Upstream up to 10.0 → Maistro residual ~3 (Reduced).** A compromised dependency lands in a
disposable, egress-constrained guest with bounded authority and a recorded audit trail, not as host
root with a botnet implant.

**Residual risk / gaps.** microVM (ADR-093) and signing (ADR-069/070/083) are **Specified, migration
in progress**; supply-chain malware "mostly doesn't need to escape" — it exfiltrates what's reachable
*inside* the sandbox (ADR-093 §survey #3), so the residual is dominated by in-sandbox secrets/egress
hygiene, not the boundary. **Status: Specified.**

---

## 8. Transparent credential / traffic exfiltration via shared config

**Anchor CVE.** LangSmith **"AgentSmith"** (CVSS 8.8) — a malicious **proxy setting** on a prompt
uploaded to the public LangChain Hub silently intercepted traffic of anyone who adopted the prompt,
harvesting OpenAI API keys, prompt data, and attachments, transparently and persistently.

**How our design changes the outcome.**
- **Credentials never travel inside shared artifacts.** Per-user credentials are encrypted
  (`maistro.credentials`) and provider keys live in the vault with a redaction layer (ADR-064);
  importing a shared prompt/skill cannot carry a usable key or silently rebind your egress.
- **Egress allow-list + bidirectional Warden** mean a prompt/tool can't redirect traffic to an
  attacker proxy without tripping a denied-egress event.
- **Skills/MCP trust gate** (ADR-083): an imported community artifact is untrusted-by-default and
  verify-gated, so a "malicious proxy config" rides in as an inspected, signed change — not an
  invisible setting.

**Upstream 8.8 → Maistro residual ~3 (Reduced).** The transparent-interception primitive (silently
rebind everyone's traffic via a shared config) is broken by egress allow-listing + credential
isolation.

**Residual risk / gaps.** Depends on egress allow-listing being enforced by default (entry 4 gap) and
on the verify-gate covering the prompt/skill import path. **Status: Mixed.**

---

## 9. Memory / learned-policy poisoning

**Context.** Agent memory and *learned* policy are an attack surface: poison the episodic/learnings
store or nudge a learned routing/safety policy until it drifts into attacker-favorable behavior.

**How our design changes the outcome.**
- **Scoped memory** (ADR-013): `global → org → team → user → agent → session` isolation limits
  cross-scope poisoning; PII tiers (ADR-055) bound what memory can hold.
- **The deconfliction immune system** (ADR-074): a learned policy that drifts against a
  safety-critical ADR is treated as a *poisoning signal* — held for admin review, **not** silently
  applied. Every learned/RBAC policy change must pass the ADR-070 Rehearse/verify gate (ADR-073).
- **Admin-scoped policy + audit** (ADR-068/073): an agent principal can neither read the approver
  matrix nor forge a decision record, so it can't quietly rewrite the rules it operates under.

**Upstream n/a → Maistro residual ~3 (Reduced).** Drift becomes a detected, gated event with a signed
audit trail rather than a silent capability change.

**Residual risk / gaps.** ADR-074 deconfliction and the Rehearse gate are **Specified**; the immune
system only catches drift *against an encoded safety ADR* — poisoning that stays within policy
bounds, or memory poisoning of non-policy learnings, is detection-limited. **Status: Specified.**

---

## 10. Excessive agency / over-privileged tool use

**Context.** OWASP LLM06 / agentic "excessive agency": an agent (or a drifting learned policy) holds
more authority than the task needs, so any compromise (entries 5–9) cashes out larger.

**How our design changes the outcome.**
- **Authority envelope** (ADR-068): an agent holds a *subset* of its owner's authority; an
  injected/compromised request cannot exceed the principal's authority — the named property-test
  invariant the threat model leans on.
- **Reversibility + approval gates** (ADR-050/051): tools default `irreversible`; destructive/elevated
  actions hit the Sentinel gate (tier ladder → approver matrix → budget veto) before executing.
- **Dangerous-tool/command screening** (`security/dangerous_tools.py`, `patterns.py`): dangerous
  commands, tool names, and blocked host paths are screened; per-task grants are TTL-bounded and
  command-allow-listed (entry 7).

**Upstream n/a → Maistro residual ~3 (Reduced).** Blast radius of any single compromise is bounded by
least-authority + reversibility gates + budget veto.

**Residual risk / gaps.** Gate effectiveness depends on the approver matrix and θ-thresholds being
tuned correctly (ADR-073 declarative layer); a misconfigured policy widens authority. Reversibility
classification is only as good as the per-tool taxonomy coverage (ADR-050). **Status: Implemented**
(core enforcement exists; tuning is operational).

---

## Cross-cutting: why the *class* mostly doesn't reach us

The recurring root cause across Langflow/Flowise/n8n/MCP-Inspector is a single anti-pattern:
**an interpreter (Python `exec`, JS `eval`, workflow-expression engine) exposed on a network
boundary, under weak auth, with host-level reach.** Our architecture refuses each leg of that
independently:

1. **No host-context interpreter on a request path** (entry 1) — the primitive doesn't exist.
2. **Auth + Sentinel adjudication on every boundary** (ADR-068) — no "validate"/"debug" path skips
   authz.
3. **Fail-closed microVM isolation for any code we didn't write** (ADR-093) — host reach is removed
   even when execution is intended.
4. **Untrusted-by-default + bidirectional Warden + egress allow-list** (ADR-072/073) — content and
   traffic are quarantined and bounded in both directions.

The honest caveats, repeated because they matter: **prompt-injection detection is heuristic**
(entries 5–6 lean on containment, not detection), and several boundary controls (microVM migration
SPEC-190, signing/trust-gate ADR-083/069/070, egress allow-listing, web-session ADR-077) are
**Specified and partially implemented** — their residual scores assume completion of the work tracked
in those documents. This ledger should be re-scored as that work lands.

---

## Entry template

```markdown
## N. <attack class>

**Anchor CVE(s).** <CVE-id (CVSS)> — <one-line root cause>. Generalize to the attack class.

**How our design changes the outcome.**
- <control> (<ADR/SPEC/code ref>): <why it removes or shrinks the flaw>

**Upstream <X> → Maistro residual ~<Y> (<band>).** <one-line rationale>

**Residual risk / gaps.** <the honest exposure>. **Status: Implemented | Specified | Mixed.**
```

---

## Sources

- VentureBeat — *7,000 Langflow servers under attack; LangGraph, LangChain same holes* (2026).
- Langflow RCE `CVE-2025-3248`: Zscaler ThreatLabz; Trend Micro (Flodrix botnet); NVD; CISA KEV.
- Langflow account-takeover/RCE `CVE-2025-34291`: Obsidian Security.
- Flowise `CVE-2025-59528` (CVSS 10.0): The Hacker News; CSO Online; VulnCheck.
- n8n `CVE-2025-68613` (CVSS 9.9): The Hacker News; Orca Security; Resecurity.
- LangChain "LangGrinch" `CVE-2025-68664` (CVSS 9.3): Cyata; The Hacker News; NVD; Miggo.
- LangChain SSRF `CVE-2023-46229`; RCE `CVE-2024-36480`.
- LangSmith "AgentSmith" (CVSS 8.8): Noma Security; The Hacker News.
- MCP threat taxonomy / tool poisoning / rug-pull / confused deputy: eSentire; Checkmarx Zero; Simon
  Willison; `CVE-2025-49596` (MCP Inspector).
- EchoLeak `CVE-2025-32711` (CVSS 9.3): Aim Security; arXiv 2509.10540; HackTheBox; Sentra.
- Internal: ADR-028, ADR-050, ADR-051, ADR-058, ADR-059, ADR-064, ADR-068, ADR-069, ADR-070,
  ADR-072, ADR-073, ADR-074, ADR-077, ADR-083, ADR-093; SPEC-011, SPEC-183, SPEC-190;
  `security/external_content.py`, `security/gate.py`, `security/trust_boundary.py`,
  `security/dangerous_tools.py`, `vault.py`.
```
