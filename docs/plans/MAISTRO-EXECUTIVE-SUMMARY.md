# Maistro Launch Initiative — Executive Summary

**Status:** Pre-launch analysis complete; six-phase remediation plan defined; critical findings documented  
**Last updated:** 2026-06-15  
**Working branch:** `develop` (production); releases to tagged `main`  
**Plan of record:** [`MAISTRO-LAUNCH-BUILDERS-RSI-SECURITY-PLAN.md`](MAISTRO-LAUNCH-BUILDERS-RSI-SECURITY-PLAN.md)

---

## The Situation

Maistro is an excellent architecture for self-improving agent systems, but current implementation has four critical gaps before HackerNews launch:

1. **Hygiene:** git history and current tree contain Disney emails, personal infrastructure, hardcoded credentials, 15 MB of committed node_modules, no license file, and inaccurate deployment instructions.

2. **Isolation:** Builders operates on the live repository; RSI uses Docker as a "microVM" (it's not); both skip the central sandbox protocol and fail gracefully into weaker isolation. Generated code can read/modify the controller's repository.

3. **Self-improvement:** Evolve benchmarks are labeled "real" but use heuristic/proxy scoring. RSI quarantine is optional. Neither has mandatory external approval gates. The system can overfit and promote itself on weak evidence.

4. **Security claims:** The public README and docs claim VM-grade isolation, sandboxed execution, and policy enforcement. The actual code paths use shared-kernel Docker, host subprocesses, and optional checks. The threat model is Proposed but docs speak as if controls are live.

**The fix:** Six phases of targeted work that fix each gap without architectural redesign. The plan is proven feasible on `develop` (RSI PoC, Evolve mechanis, AutonomousCampaign structure already tested).

---

## Why This Matters

Maistro's value proposition is **trustworthy self-improvement**: autonomous code generation, testing, and promotion with mandatory safety gates. If the isolation is weak or the benchmarks are fake, the whole story collapses—and so does trust at launch.

The plan doesn't add features. It makes the current architecture honest and safe.

---

## Six Phases (Execution Order)

### **Phase 0: Establish Truth (1-2 weeks)**
Stop adding contradictory claims while cleanup proceeds.

- [ ] Add public capability matrix: `Implemented | Experimental | Planned | Unsafe`
- [ ] Mark Builders, RSI, real-benchmark adapters, VM sandbox backends as `Experimental` until their gates pass
- [ ] Rewrite docs that mislabel worktrees/containers/heuristics as secure/real
- [ ] Decide canonical product name (Maistro Engine vs. Hive Conductor) and public branch strategy

**Exit gate:** Reviewer can tell what works today, what is experimental, and what is planned *without reading source*.

---

### **Phase 1: Hacker News Launch Hygiene (2-3 weeks)**
Clean tree, clean history, reproducible installer, honest README.

**1A. Sanitize current tree:**
- Delete `scripts/scrub-and-push-upstream.py`
- Replace Disney/JEDAI references with generic fixtures
- Remove hardcoded `coinswarm_dev_2024` password
- Add real Apache-2.0 `LICENSE` file
- Rewrite README around one verified quick start + honest architecture
- Archive historical audits with dates and status
- Remove internal planning clutter not useful to public users

**1B. Clean reachable history:**
- Create protected backup mirror before rewriting
- Use `git filter-repo` to remove scrub script, sensitive content, committed `node_modules`, 15 Disney-email commits
- Re-author Disney emails; remove sensitive co-author trailers
- Re-run full-history secret/PII/author-email/blob scans after rewrite

**1C. Make installer reproducible:**
- Implement SPEC-207 (common Ubuntu guest installer + Docker Sandboxes)
- Implement SPEC-208 (desktop broker without host socket access)
- Implement SPEC-209 (Cloudflare configurator → signed manifest → stable bootstrap)
- Remove Docker socket from official deployment
- Make `get.sh` consume signed/tagged release manifest, not moving `develop`
- Add clean-machine installer smoke tests

**Exit gate:** Fresh clone, quick start, install script, tests, links, and security claims all work as documented. Full-history scan reports no prohibited content.

---

### **Phase 2: Real Builders Execution Boundary (3-4 weeks)**
Builders becomes a separate control plane; untrusted code runs in ephemeral isolated workers.

**2A. Unify execution:**
- Make `SandboxProtocol` the only interface used by Builders, RSI, benchmarks
- Route each workload through `SandboxSelector` with explicit policy
- Require `UNTRUSTED_CODE` for generated tests, generated code, arbitrary commands
- Remove lazy fallback from `LocalWorktreeSandbox`; fail closed without explicit trusted mode

**2B. Implement ephemeral workers:**
- Implement Docker Sandboxes backend as official installer default
- Give each worker immutable base image + fresh workspace
- Clone target revision *inside* worker, not on controller
- Deny network by default; grant time-limited allowlisted egress only for dependency/research phases
- No host bind-mounts; no raw socket access
- Enforce CPU/memory/disk/wall-time/output-size budgets
- Export only typed artifacts: diff, test report, logs, provenance

**2B.1 Claude Code-style capability without ambient privilege:**
- Preserve workspace read/write, arbitrary in-VM argv, local Git, durable resume via pinned-base-plus-patch
- Prohibit raw host filesystem, runtime sockets, direct push/merge
- (Backlog: dependency-fetch VM, research broker, private-repo broker, browser sandbox, service labs)

**2C. Make separate mode usable:**
- Replace `maistro-builders:latest` with digest-pinned release image
- Add status, cancel, inspect, resume, teardown operations
- Resume = pinned base commit + binary patch replay into fresh offline VM
- Add end-to-end tests proving live repo and host marker cannot be read/modified

**Exit gate:** Malicious repo test cannot read host marker, reach host socket, retain credentials, or survive teardown. Builders can clone `develop`, edit, test, produce diff without touching controller checkout.

---

### **Phase 3: Portable Git Runtime (1-2 weeks)**
Every ephemeral builder and executable benchmark includes known-good pinned Git.

- [ ] Define `GitRuntime` contract: version, platform, checksum, capabilities, config policy, provenance
- [ ] Produce pinned Linux multi-architecture Git runtime layer or tarball
- [ ] Produce pinned MinGit artifact for Windows-native workers
- [ ] Include CA certs; exclude credential helpers, stored credentials, user/system git config
- [ ] Set safe defaults: isolated `HOME`, `GIT_CONFIG_NOSYSTEM=1`, empty credential helper, disabled hooks, no push credentials, allowlisted protocols
- [ ] Sign artifact, publish checksums + SBOM, pin by digest in worker images
- [ ] Add conformance tests: clone, checkout, branch, diff, commit, worktree, offline operation, denied push, absent credentials
- [ ] Use same runtime in Builders, RSI, SWE-bench, TerminalBench, other code-oriented benchmarks

**Exit gate:** Every worker reports expected git version and passes GitRuntime conformance suite without host git access.

---

### **Phase 4: Make RSI and Evolve Trustworthy (3-4 weeks)**
Self-improvement becomes a verifiable, auditable, approval-gated process.

**4A. Fix RSI containment and promotion:**
- [ ] Change RSI default base branch to `develop`
- [ ] Execute clone, branch, patch, test, diff, commit through sandbox protocol inside worker
- [ ] Capture candidate patch from `base_ref...candidate_ref`, not `git diff` after commit
- [ ] Make quarantine *mandatory*; remove `quarantine_check is None` bypass
- [ ] Instantiate Warden and adversarial review outside candidate-controlled worker
- [ ] Prevent worker credentials from pushing or opening PRs
- [ ] Return proposal artifact to separate, minimally privileged publisher after human approval
- [ ] Add rollback, attempt provenance, immutable logs, budget limits, kill switch

**4B. Implement benchmark fidelity:**
- [ ] Implement SPEC-202 `stub | proxy | real` taxonomy in types, metadata, logs, UI
- [ ] Rename `REAL_BENCHMARKS` to `PROXY_BENCHMARKS`
- [ ] Remove `metadata.runner="real"` from heuristic adapters
- [ ] Prohibit stub/proxy results from promotion
- [ ] Make baseline and candidate use identical dataset version, seed, image, dependency cache, resource budget
- [ ] Implement official real adapters incrementally (start with deterministic non-execution benchmarks)
- [ ] Run SWE-bench, TerminalBench, OSWorld only in ephemeral benchmark workers
- [ ] Record dataset revision, harness revision, image digest, git revision, model, cost, duration, fidelity in every result

**4C. Join RSI and Evolve safely:**
- [ ] Let Evolve optimize prompts/topology/config using fidelity-gated results
- [ ] Let RSI propose code changes only after Evolve identifies reproducible weakness
- [ ] Expose Evolve evaluation as autonomous Builders capability (fresh `BENCHMARK_EVAL` VMs, read-only signed harness/dataset, no promotion)
- [ ] Expose RSI candidate generation as autonomous Builders capability (fresh `UNTRUSTED_CODE` VMs, return pinned-base-plus-patch artifacts)
- [ ] Keep orchestration, baseline/candidate comparison, quarantine, promotion outside candidate VMs
- [ ] Require: passing tests, real-benchmark improvement, no security regression, no cost/latency regression, quarantine clearance before promotion
- [ ] Use holdout benchmarks to reduce overfitting
- [ ] Require repeated wins across multiple runs before calling candidate improved
- [ ] Run `maistro-rsi` and `maistro-evolve` tests, types, fidelity checks in required `develop` CI

**Exit gate:** Full cycle can improve Maistro from `develop` inside VM-grade worker, return reviewed proposal, prove improvement with real reproducible benchmark evidence.

---

### **Phase 5: Reconcile Security Claims with Enforcement (2-3 weeks)**
Every security statement has an enforced control, test, owner, and documented residual risk.

- [ ] Create claim-to-control matrix from README, deployment stance, ADR-072, ADR-093, security docs
- [ ] Remove host Docker socket from all official deployments
- [ ] Wire `SandboxSelector` into every untrusted execution path
- [ ] Remove non-VM fallback for workloads whose policy requires VM isolation
- [ ] Apply Sentinel/trust-boundary authorization to Builders, git, sandbox, RSI, benchmark, MCP tool calls
- [ ] Make Canvas auth reject missing/invalid keys, never default to admin
- [ ] Make webhook routes reject requests when auth secret is unset or don't mount them
- [ ] Ensure every external-content ingress and tool-result egress uses intended Warden/Sentinel path
- [ ] Replace source defaults for credentials with explicit dev-only configuration
- [ ] Pin base images, GitHub Actions, downloaded tools, installer artifacts by digest/version
- [ ] Add sandbox escape, egress, socket, credential, teardown, policy-bypass tests
- [ ] Gate `develop` with SAST, dependency audit, full-history secret scan, sandbox conformance, RSI/Evolve tests, release bundle smoke tests
- [ ] Accept ADR-072 only after checklist is satisfied by linked tests

**Exit gate:** Claim-to-control matrix contains no unowned or untested critical claim. Public docs describe residual risks (self-hosted mode, experimental self-improvement).

---

### **Phase 6: HN Launch Gate (1 week)**
Ship the release with full confidence.

- [ ] Tag and sign release candidate from `main`
- [ ] Test exact public install instructions on clean machines
- [ ] Verify no private links, personal data, employer references, stale screenshots, broken links, dead commands remain
- [ ] Publish honest limitations section: sandbox availability, experimental self-improvement, persistence, supported deployment profiles
- [ ] Prepare short architecture/security explanation backed by claim-to-control matrix
- [ ] Confirm required CI checks are green on release tag
- [ ] Freeze release artifacts and checksums before posting

---

## First Implementation Sequence (This Sprint)

1. **Add public capability matrix** (Phase 0) — PRIORITY 1
   - Update AGENTS.md with Implemented/Experimental/Planned/Unsafe columns
   - Mark Builders, RSI, real-benchmark adapters, VM sandbox backends Experimental

2. **Sanitize current tree** (Phase 1A) — PRIORITY 1
   - Delete `scripts/scrub-and-push-upstream.py`
   - Add real `LICENSE` file
   - Fix README: accurate package count, install claims, links

3. **Add launch-audit CI** (Phase 1C) — PRIORITY 1
   - New CI job: scans tree for secrets, PII, forbidden files, large blobs, dead links, README command drift
   - Run on every `develop` commit

4. **Remove Builders TUI live-repo fallback** (Phase 2A) — PRIORITY 2
   - Remove lazy fallback from `LocalWorktreeSandbox`
   - Fail closed when VM sandbox unavailable
   - Label local worktree as trusted-development-only

5. **Wire Builders/RSI/benchmarks to SandboxSelector** (Phase 2A) — PRIORITY 2
   - Route all untrusted code execution through central protocol
   - Require explicit policy (e.g., `UNTRUSTED_CODE`)

6. **Define and produce portable Git runtime** (Phase 3) — PRIORITY 3
   - Define `GitRuntime` contract
   - Produce pinned Linux/Windows artifacts
   - Write conformance tests

7. **Make RSI quarantine mandatory** (Phase 4A) — PRIORITY 3
   - Remove `quarantine_check is None` bypass
   - Instantiate Warden outside worker

8. **Implement benchmark fidelity taxonomy** (Phase 4B) — PRIORITY 3
   - Rename `REAL_BENCHMARKS` → `PROXY_BENCHMARKS`
   - Fail closed on unknown benchmarks
   - Prohibit proxy/stub promotion

---

## Success Criteria

- [ ] Fresh clone and install work exactly as documented
- [ ] Security claims are backed by live code paths and tests, not promises
- [ ] Generated code cannot read/modify the live repository or access the controller's Docker socket
- [ ] RSI promotion requires external human approval outside the candidate-controlled VM
- [ ] All benchmarks use real, reproducible, fidelity-marked evidence
- [ ] Full-history scan reports no prohibited content
- [ ] HN readers can tell what works today, what is experimental, and what is planned without reading source
- [ ] Residual risks are documented and honest

---

## Key References

- **Full plan:** [`MAISTRO-LAUNCH-BUILDERS-RSI-SECURITY-PLAN.md`](MAISTRO-LAUNCH-BUILDERS-RSI-SECURITY-PLAN.md)
- **Durable constraints:** [`.cursor/context/maistro-focus.md`](../../.cursor/context/maistro-focus.md)
- **Critical findings:** [Memory: `critical_findings_baseline.md`]
- **Architecture decisions:** `docs/adr/` (ADR-093, ADR-098, ADR-099, ADR-097, SPEC-200, SPEC-202, SPEC-207, SPEC-208, SPEC-209)

---

## How to Use This Plan

1. **Before starting any work:** Read `.cursor/context/maistro-focus.md` for the non-negotiable rules
2. **When implementing builders/RSI/benchmarks:** Refer to the relevant phase checklist
3. **When claiming something is secure/real/implemented:** Check the claim-to-control matrix and the corresponding checkpoint in Phase 5
4. **When stuck:** Escalate to the plan of record and update it if the finding is new

**Questions?** Every item in this plan links to an ADR/spec or has a test command in the full plan document.
