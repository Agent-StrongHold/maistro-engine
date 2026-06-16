# Maistro Launch, Builders, RSI, and Security Plan

**Status:** Living plan of record  
**Working branch:** `develop`  
**Baseline reviewed:** `0af6e62` on 2026-06-11  
**Primary objective:** Make Maistro honest, launchable, and capable of improving itself without giving generated code access to the host or promoting changes on weak evidence.

This plan is the source of truth for work in the four focus areas below. Update it when a finding is fixed, a decision changes, or a new launch blocker is found.

## Focus Areas

1. Prepare a credible Hacker News launch:
   - no sensitive or embarrassing current-tree content;
   - no avoidable sensitive or bloated reachable history;
   - no README, installer, security, or deployment claims that the code does not satisfy;
   - no stale internal plans or dead workflows presented as product surface.
2. Make Builders a separate, usable execution mode that operates only on isolated ephemeral codebases.
3. Make RSI and Evolve improve Maistro using trustworthy benchmarks and mandatory safety gates.
4. Reconcile the implemented security controls with the claimed security posture.

## Non-Negotiable Rules

- Active development happens on `develop`. Launch candidates are promoted from `develop` to a tagged release on `main`.
- A git worktree is an isolation convenience, not a security sandbox.
- A shared-kernel container is not sufficient for untrusted model-generated code under the accepted Maistro posture.
- Untrusted code and executable benchmarks must use the central sandbox protocol with a policy requiring VM-grade isolation, or fail closed.
- The accepted simple Linux installer target is the complete Maistro stack inside an Ubuntu Server
  24.04 LTS x86-64 VM with nested KVM, using Docker Sandboxes for untrusted execution.
- The Proxmox helper only provisions that Ubuntu VM and invokes the common guest installer. Custom
  sandbox and hypervisor providers remain backlog work.
- The accepted Windows/macOS installer target is containerized Maistro plus a signed narrow host
  sandbox broker. Maistro containers never receive the host Docker socket or arbitrary host paths.
- The accepted public installer is the Cloudflare web configurator from ADR-099/SPEC-209. It emits a
  stable bootstrap command plus a signed secret-free manifest, never arbitrary generated shell.
- No builder, RSI cycle, benchmark, or agent may receive the host Docker socket.
- No self-improvement result may push, open a PR, merge, or promote itself without mandatory quarantine, trustworthy evaluation, and an external approval gate.
- Stub and proxy benchmark results may support development, but may never be described as real or used for promotion.
- Security and deployment claims require a live code path plus tests. Proposed ADRs and unwired primitives are not controls.
- Public documentation must describe current behavior and clearly label planned behavior.

## Verified Baseline

### Launch Hygiene

The existing `docs/audit/HN-LAUNCH-AUDIT.md` is directionally correct but already stale in places. The following blockers remain in the current tree or reachable history:

- `scripts/scrub-and-push-upstream.py` still contains the sensitive values it claims to scrub.
- Disney/JEDAI references, personal infrastructure details, LAN addresses, and a personal domain remain in tracked files.
- `packages/maistro-canvas/frontend/server.js` still contains the hardcoded `coinswarm_dev_2024` password.
- There is no `LICENSE` file while README and other docs claim Apache 2.0.
- README and `CLAUDE.md` contain inaccurate package counts, ADR counts, branch guidance, links, and install claims.
- Root-level internal artifacts such as `AUDIT.md`, `CONSOLIDATION-PLAN.md`, `cutover/`, `design/`, and demo/overnight notes create a confusing first impression and expose stale implementation details.
- `get.sh` claims to download a release, but always downloads moving `develop`; its `VERSION` variable is unused.
- `get.sh` downloads `litellm_config.yaml`, which does not exist in the root tree, while `docker-compose.yml` requires it.
- The official install path uses the root compose file that mounts `/var/run/docker.sock`, contradicting `docs/product/DEPLOYMENT-STANCE.md`.
- Security, quality, registry, and mutation workflows do not consistently gate `develop`. Some workflows still reference nonexistent `container_registry/user_containers/sandbox_templates/...` paths.
- Reachable history includes 15 commits authored with a Disney email plus Disney/JEDAI text in commit bodies and trailers.
- Reachable history contains committed `node_modules` blobs, including an 11 MB `esbuild` binary and multiple multi-megabyte JavaScript bundles.

### Builders

There are currently three partially overlapping builder execution concepts:

- `maistro.builders`: the core stage machine and contracts.
- `maistro_bootstrap.builders.LocalWorktreeSandbox`: the interactive Builders implementation.
- `maistro.cli._container.SessionLifecycle`: a container session lifecycle using `maistro-builders:latest`.

They are not one enforced execution path.

Critical findings:

- The Builders TUI creates `LocalWorktreeSandbox(Path("."))` without entering its context manager. Its lazy fallback therefore reads, writes, and executes against the live repo.
- Even when the worktree context is used, `SandboxedShell` executes host processes with only `cwd` and environment restrictions. Running project tests can execute arbitrary repository code with the host user's permissions.
- `run_argv` intentionally skips the free-form command checks. This is acceptable only inside a real sandbox, not on the host.
- `Dockerfile.builders` is not wired into the lifecycle or compose files. It is root, network-enabled, unpinned, and sleeps forever.
- The container lifecycle stores `repo_url` as a label but does not clone the repo into the session volume.
- The new central `SandboxProtocol`, policies, and selector exist, but only the fake backend is implemented and selector use is limited to tests.
- SPEC-200 is marked Implemented even though its security objective is not met by the live TUI path.

### RSI and Evolve

Critical findings:

- `DockerMicroVmSandbox` is a Docker container adapter, not a microVM.
- `RsiCycle` directly calls that Docker adapter instead of the central sandbox selector and `UNTRUSTED_CODE` policy.
- RSI git operations execute as host subprocesses through `maistro.tools.git.server`; they do not execute through the RSI sandbox protocol.
- `RsiCycle` never supplies `quarantine_check` to `run_self_branch_attempt`.
- `run_self_branch_attempt` treats a missing quarantine check as cleared and may open a PR.
- The diff is captured with plain `git diff` after `git_commit`, which normally produces an empty diff. That undermines path detection and quarantine review.
- RSI defaults to `base_branch="main"` even though Maistro work happens on `develop`.
- The runner can only destroy the Docker sandbox; host-side clone, branch, commit, push, and PR effects are outside that teardown boundary.
- Current Evolve adapters are registered as `REAL_BENCHMARKS` and emit `metadata={"runner": "real"}`, but use handwritten samples, keyword heuristics, LLM judging, and random fallback scoring.
- Evolve silently skips unknown benchmark names.
- The Hive evolution service runs `EvalHarness(use_real_benchmarks=True)`, so it treats proxy scores as real in a live background loop.
- SPEC-202 correctly identifies the benchmark fidelity problem, but remains Proposed and unimplemented.
- CI does not run `maistro-evolve` or `maistro-rsi` tests in the primary test job and does not type-check `maistro-rsi`.

### Portable Git

Git is already installed in `Dockerfile.builders` through `apt`, but this does not satisfy the builder requirement:

- the version is not pinned;
- the artifact is not portable or reusable by every sandbox backend;
- its provenance, checksum, SBOM, and signature are not recorded;
- no conformance test proves git exists in every ephemeral builder and benchmark sandbox;
- no hardened git configuration prevents credential helpers, host config, pushes, unsafe protocols, or unintended network access;
- the image itself is not connected to the Builders execution path.

### Security Posture

Controls that are genuinely present include fail-fast API auth startup, network-disabled Docker sandbox defaults, environment allowlisting, input/output scanning in several agent strategies, non-root API images, and fail-closed behavior in the new sandbox selector.

The following claims are not enforced end to end:

- Accepted ADR-093 requires VM-grade isolation for untrusted code, but Builders uses host subprocesses, RSI uses Docker, the tool sandbox uses Docker, and Hive's executor permits a hardened-container fallback.
- The official deployment stance forbids the host Docker socket, but the official root compose and API image are designed around it.
- The central sandbox selector is not wired into production execution paths.
- The trust-boundary `check_permission` implementation is used by tests but not by git, sandbox, Builders, or RSI execution.
- Sentinel is used by selected agent strategies, not every tool boundary.
- Warden is not mandatory for Builders actions or RSI promotion.
- Canvas standalone auth accepts any API key and returns an admin principal.
- GitHub and CI webhook authentication fails open when secrets are unset.
- Security workflows do not gate `develop`, and DAST/mutation paths are stale.
- The threat model is Proposed and its acceptance checklist is unchecked, while public docs speak as if all boundaries are enforced.

## Execution Plan

### Phase 0: Establish Truth and Freeze Claims

Goal: stop adding contradictory claims while cleanup and isolation work proceeds.

- [ ] Add a public capability/status matrix: `Implemented`, `Experimental`, `Planned`, `Unsafe for untrusted code`.
- [ ] Mark Builders, RSI, Evolve real-benchmark adapters, and VM sandbox backends Experimental until their gates below pass.
- [ ] Change docs that call local worktrees, Docker containers, or heuristic benchmarks secure/real.
- [ ] Add a rule that an ADR/spec cannot be marked Implemented without a linked live integration path and test.
- [ ] Decide the one public product name and the relationship between Maistro Engine and Hive Conductor.
- [ ] Decide which public branch is displayed by GitHub. Continue work on `develop`; publish HN releases from tagged `main`.

Exit gate:

- A reviewer can tell what works today, what is experimental, and what is planned without reading source.

### Phase 1: Hacker News Launch Hygiene

#### 1A. Sanitize the current tree

- [ ] Delete `scripts/scrub-and-push-upstream.py`.
- [ ] Replace Disney/JEDAI demo data, names, URLs, and work-machine paths with generic fixtures.
- [ ] Replace personal domains and LAN IP defaults with `example.com`, loopback, or required environment variables.
- [ ] Remove the hardcoded canvas database credential and require configuration.
- [ ] Add a real Apache-2.0 `LICENSE` file or change every license claim before launch.
- [ ] Rewrite README around one verified quick start and one honest architecture story.
- [ ] Fix package count, ADR count, branch flow, Python version, links, and PyPI/install claims.
- [ ] Archive historical audits under `docs/audit/` with explicit dates and remediation status.
- [ ] Remove, relocate, or summarize internal planning clutter that is not useful to public users.
- [ ] Remove links to inaccessible private repos or label them explicitly.

#### 1B. Clean reachable history

Because the repository is already public, history rewriting does not erase exposure. Rotate any value that may be sensitive before rewriting.

- [ ] Create a protected backup mirror before rewriting.
- [ ] Use `git filter-repo` to remove the scrub script, sensitive historical content, and committed `node_modules`.
- [ ] Re-author Disney-email commits and remove sensitive co-author trailers.
- [ ] Review commit subjects/bodies for private infrastructure, personal finance, customer/employer names, and dead experiments.
- [ ] Force-push only after documenting the rewrite and coordinating all active clones.
- [ ] Re-run full-history secret, PII, author-email, and large-blob scans after the rewrite.
- [ ] Prefer a fresh sanitized public release repository if preserving the existing public history is less valuable than a clean launch boundary.

#### 1C. Make launch paths reproducible

- [x] Accept ADR-097: one simple Linux install envelope using an Ubuntu VM plus Docker Sandboxes.
- [x] Accept ADR-098: one simple Windows/macOS install envelope using containerized Maistro plus the
  narrow host Docker Sandboxes broker.
- [x] Accept ADR-099: Cloudflare web configurator resolves selections into signed declarative
  manifests consumed by a stable audited bootstrap.
- [ ] Implement `docs/plans/WEB-INSTALLER-DELIVERY-PLAN.md`.
- [ ] Implement SPEC-207 common Ubuntu guest installer with nested-KVM and Docker Sandboxes preflight.
- [ ] Implement the thin Proxmox helper that provisions the Ubuntu VM and invokes the guest installer.
- [ ] Implement SPEC-208 signed desktop broker, containerized control-plane bundle, authenticated
  local transport, project registration, and conformance.
- [ ] Fail closed when the supported VM envelope or Docker Sandboxes conformance is unavailable.
- [ ] Make `get.sh` consume a signed/tagged release manifest, not moving `develop`.
- [ ] Make every required installer file mandatory; fail before startup when a bundle member is missing.
- [ ] Remove the Docker socket from the official deployment path.
- [ ] Add clean-machine installer smoke tests for Linux and macOS.
- [ ] Add a launch audit CI job that scans current tree and full history for secrets, PII patterns, forbidden files, large blobs, dead links, and README command drift.
- [ ] Make CI, quality, security, registry, and sandbox conformance gates run on `develop`.
- [ ] Delete or repair stale DAST/mutation workflow paths.

Exit gate:

- Fresh clone, quick start, install script, tests, links, and security claims all work as documented.
- Full-history scan reports no prohibited content or accidental generated dependency trees.
- The HN-linked release is a signed immutable tag with green required checks.

### Phase 2: Build the Real Builders Execution Boundary

Goal: Builders becomes a separate control plane that leases isolated ephemeral workers.

#### 2A. Unify execution

- [ ] Make `maistro.sandbox.SandboxProtocol` the only execution interface used by Builders, RSI, and executable benchmarks.
- [ ] Route each workload through `SandboxSelector` with an explicit policy.
- [ ] Require `UNTRUSTED_CODE` for Mason, Archie, generated tests, generated code, and arbitrary commands.
- [ ] Keep local worktree mode only as an explicitly named trusted-development mode. It must never be called secure or used automatically.
- [ ] Remove lazy fallback from `LocalWorktreeSandbox`; using it without entering a workspace must fail closed.
- [ ] Ensure every agent action carries an execution-context decision and an audit record.

#### 2B. Implement ephemeral workers

- [ ] Implement the Docker Sandboxes backend as the official installer default and pass conformance.
- [ ] Implement the desktop broker client adapter without exposing host Docker or arbitrary host
  filesystem authority to Maistro containers.
- [ ] Keep Proxmox sibling VMs, Incus/libvirt, gVisor, Kata, Firecracker, and managed sandbox
  providers in the custom-deployment backlog until the default path works.
- [ ] Give each worker an immutable base image plus a fresh writable workspace.
- [ ] Clone or materialize the target revision inside the worker, not on the controller host.
- [ ] Deny network by default; grant time-limited allowlisted egress only to explicit research/dependency phases.
- [ ] Never raw-bind-mount host project paths or runtime sockets.
- [ ] Enforce CPU, memory, PID, disk, wall-time, output-size, and total-cost budgets.
- [ ] Destroy workers on success, failure, cancellation, and controller restart.
- [ ] Export only typed artifacts: diff/patch, test report, benchmark report, logs, and provenance.

#### 2B.1 Preserve Claude Code-style capability without ambient privilege

The offline execution VM is the default lane, not the only lane. A secure Builder must remain useful
for real coding while keeping untrusted code away from the controller and unrestricted egress.

- [x] Preserve workspace read/write, arbitrary in-VM argv execution, local Git operations, model
      inference, and durable resume through pinned-base-plus-patch replay.
- [x] Prohibit raw host filesystem access, runtime sockets, and direct push/merge from the Builder VM.
- [ ] Add a disposable dependency-fetch VM with time-limited allowlisted egress; import only a scanned
      dependency/cache artifact into the offline execution VM.
- [ ] Add a read-only research/docs broker that returns sanitized content without giving generated
      code a general network socket.
- [ ] Add a private-repository clone broker using a short-lived, repository-scoped credential that
      exists only in the materialization VM and is destroyed before execution.
- [ ] Add allowlisted controller-side MCP/external-tool brokers with authorization and audit records.
- [ ] Add a separate browser sandbox for browser automation.
- [ ] Add per-session isolated service labs for database/API/integration tests without exposing host
      services or public egress.

Capability rule:

- Do not solve a missing capability by weakening the offline VM or exposing the controller.
- Do not call Builders fully Claude Code-compatible until dependency, research, private-repo,
  external-tool, browser, and service-lab lanes are implemented and tested.
- Normal coding inside the disposable offline VM is autonomous and must not prompt per command.
- Boundary capabilities use controller-issued, scoped, expiring session leases. Prefer one approval
  such as "allow PyPI and npm for 20 minutes" over repeated command approvals.
- Remote mutation and irreversible publication remain per-action approvals through a separate
  publisher. Host filesystem and runtime-socket access are never approvable.

#### 2C. Make the separate mode usable

- [x] Connect the live Builders TUI execution path to the central sandbox protocol and fail closed
      when no VM-grade backend qualifies.
- [x] Make create-session materialize an approved HTTPS repository in a temporary networked VM, then
      transfer it into a separate offline execution VM without host bind mounts.
- [ ] Replace `maistro-builders:latest` with a digest-pinned release image.
- [ ] Add status, cancel, inspect, resume-from-artifact, and teardown operations.
- [x] Implement resume-from-artifact as pinned base commit plus binary patch replay into a fresh
      offline VM; mutable VM/container state is not treated as durable.
- [ ] Add end-to-end tests proving the live repo and a host marker cannot be modified or read.

Exit gate:

- A malicious repository test cannot read a host marker, reach the host socket, retain credentials, or survive teardown.
- Builders can clone `develop`, edit, test, produce a diff, and return it without touching the controller checkout.

### Phase 3: Ship a Portable Git Runtime for Sandboxes

Goal: every ephemeral builder and executable benchmark has a known-good git implementation without depending on the host.

- [ ] Define a `GitRuntime` contract: version, platform, checksum, capabilities, config policy, and provenance.
- [ ] Produce a pinned Linux multi-architecture git runtime layer or tarball for sandbox images.
- [ ] Produce a pinned MinGit artifact only for Windows-native builder workers.
- [ ] Include CA certificates and only the required transport support.
- [ ] Exclude credential helpers, stored credentials, user/system git config, and Git LFS unless explicitly required.
- [ ] Set safe defaults: isolated `HOME`, `GIT_CONFIG_NOSYSTEM=1`, empty credential helper, disabled hooks, no push credentials, no recursive submodules by default, and allowlisted protocols.
- [ ] Allow fetch/clone only during an approved network phase; switch the worker to network-denied before generated code executes.
- [ ] Sign the artifact, publish checksums and SBOM, and pin it by digest in worker images.
- [ ] Add conformance tests for clone, checkout, branch, diff, commit, worktree, offline operation, denied push, and absent credentials.
- [ ] Use the same Git runtime in Builders, RSI, SWE-bench, TerminalBench, and other code-oriented benchmark images.

Exit gate:

- Every worker reports the expected git version and passes the GitRuntime conformance suite without host git access.

### Phase 4: Make RSI and Evolve Trustworthy

#### 4A. Fix RSI containment and promotion

- [ ] Change RSI default base branch to `develop`.
- [ ] Execute clone, branch, patch, test, diff, and commit through the sandbox protocol inside the worker.
- [ ] Capture the candidate patch from `base_ref...candidate_ref`, not `git diff` after commit.
- [ ] Make quarantine mandatory. Remove the `quarantine_check is None` bypass.
- [ ] Instantiate Warden and adversarial review outside the candidate-controlled worker.
- [ ] Treat changes to sandbox, RSI, Evolve, security, benchmark, workflow, and policy code as sensitive surface.
- [ ] Prevent worker credentials from pushing or opening PRs.
- [ ] Return a proposal artifact to a separate, minimally privileged publisher after human approval.
- [ ] Add rollback, attempt provenance, immutable logs, budget limits, and a kill switch.

#### 4B. Implement benchmark fidelity

- [ ] Implement SPEC-202's `stub | proxy | real` taxonomy in types, metadata, logs, and UI.
- [ ] Rename current `REAL_BENCHMARKS` to `PROXY_BENCHMARKS`.
- [ ] Remove `metadata.runner="real"` from heuristic adapters.
- [ ] Fail closed when requested benchmarks are unknown or unavailable.
- [ ] Prohibit stub/proxy results from promotion.
- [ ] Make baseline and candidate use the same dataset version, seed, environment image, dependency cache, and resource budget.
- [ ] Implement official real adapters incrementally, starting with deterministic non-execution benchmarks.
- [ ] Run SWE-bench, SWE-bench Pro, TerminalBench, and OSWorld only in ephemeral benchmark workers.
- [ ] Record dataset revision, harness revision, image digest, git revision, model, cost, duration, and fidelity in every result.
- [ ] Add self-conformance tests for every real adapter.

#### 4C. Join RSI and Evolve safely

- [ ] Let Evolve optimize prompts/topology/configuration using fidelity-gated results.
- [ ] Let RSI propose code changes only after Evolve identifies a reproducible weakness.
- [ ] Expose Evolve evaluation as an autonomous Builders capability that launches fresh
      `BENCHMARK_EVAL` VMs with read-only signed harness/dataset artifacts and no promotion ability.
- [x] Expose RSI candidate generation as an autonomous Builders capability that launches fresh
      `UNTRUSTED_CODE` VMs and returns pinned-base-plus-patch proposal artifacts.
- [ ] Keep benchmark orchestration, baseline/candidate comparison, quarantine, and promotion outside
      candidate-controlled VMs.
- [ ] Require passing tests, real-benchmark improvement, no security regression, no cost/latency budget regression, and quarantine clearance before promotion.
- [ ] Use holdout benchmarks to reduce overfitting.
- [ ] Require repeated wins across multiple runs before calling a candidate improved.
- [ ] Run `maistro-rsi` and `maistro-evolve` tests, types, and fidelity checks in required `develop` CI.

Exit gate:

- A full cycle can improve Maistro from `develop` inside a VM-grade worker, return a reviewed proposal, and prove the improvement with real, reproducible benchmark evidence.
- Once a session owner grants the bounded RSI/Evolve budget, candidate generation and evaluation run
  without per-step approvals. Only promotion/publication requires a new per-action approval.

### Phase 5: Reconcile Security Claims With Enforcement

Goal: every security statement has an enforced control, test, owner, and known residual risk.

- [ ] Create a claim-to-control matrix from README, deployment stance, ADR-072, ADR-093, and security docs.
- [ ] Remove the host Docker socket from all official deployments.
- [ ] Wire `SandboxSelector` into every untrusted execution path.
- [ ] Remove non-VM fallback for workloads whose policy requires VM isolation.
- [ ] Apply Sentinel/trust-boundary authorization to Builders, git, sandbox, RSI, benchmark, and MCP tool calls.
- [ ] Make Canvas auth reject missing/invalid keys and never default to admin.
- [ ] Make webhook routes reject requests when their authentication secret is unset, or do not mount them.
- [ ] Ensure every external-content ingress and tool-result egress uses the intended Warden/Sentinel path.
- [ ] Replace source defaults for credentials with explicit dev-only configuration where practical.
- [ ] Pin base images, GitHub Actions, downloaded tools, and installer artifacts by digest/version.
- [ ] Add sandbox escape, egress, socket, credential, teardown, and policy-bypass tests.
- [ ] Gate `develop` with SAST, dependency audit, full-history secret scan, sandbox conformance, RSI/Evolve tests, and release bundle smoke tests.
- [ ] Accept ADR-072 only after its checklist is satisfied by linked tests.

Exit gate:

- The claim-to-control matrix contains no unowned or untested critical claim.
- Public docs describe residual risks, especially self-hosted and experimental modes.

### Phase 6: HN Launch Gate

- [ ] Tag and sign a release candidate from `main`.
- [ ] Test the exact public install instructions on clean machines.
- [ ] Verify no private links, personal data, employer references, stale screenshots, broken links, or dead commands remain.
- [ ] Publish an honest limitations section covering sandbox availability, experimental self-improvement, persistence, and supported deployment profiles.
- [ ] Prepare a short architecture/security explanation backed by the claim-to-control matrix.
- [ ] Confirm required CI checks are green on the release tag.
- [ ] Freeze release artifacts and checksums before posting.

## First Implementation Sequence

These are the highest-leverage first changes, in order:

1. Sanitize current tree; add license; fix installer and README truth.
2. Add launch-audit CI on `develop`; repair stale workflows.
3. Remove Builders TUI live-repo fallback and label local mode trusted/dev-only.
4. Wire Builders/RSI/benchmarks to the central sandbox selector.
5. Build the portable Git runtime and sandbox conformance image.
6. Implement a VM-grade backend and remove Docker-socket deployment.
7. Make RSI quarantine mandatory and capture diffs correctly.
8. Implement benchmark fidelity taxonomy and prohibit proxy promotion.
9. Add required RSI/Evolve/sandbox CI on `develop`.
10. Rewrite reachable history only after the current tree and automated gates are clean.

## Required Evidence Per Completed Item

Every completed checkbox should link or point to:

- implementation path;
- test path and command;
- relevant ADR/spec update;
- CI job or release check;
- residual risk or limitation, if any.

## Verification Notes

The original baseline was produced by source, workflow, current-tree, and reachable-history inspection.

### Naive RSI mechanics proof of concept - June 11, 2026

The smallest reusable loop primitives now live in
`packages/maistro-rsi/src/maistro_rsi/experiment.py`: injected command execution, durable JSONL
measurements, a configurable quality score, and a retain/reject decision. Local proof evidence is
written under ignored `test-results/rsi-poc/`.

One manual candidate-generation iteration used the identical command for baseline and candidate:

`python -m pytest packages/maistro-evolve/tests packages/maistro-rsi/tests -q`

- Baseline: `129 passed, 25 warnings`; warning quality score `-25`.
- Proposed candidate: use Pydantic model-class `model_fields` access in Evolve fitness/crossover.
- Candidate: `130 passed, 0 warnings`; warning quality score `0`.
- Decision: accepted because the configured quality score improved without a test regression.

This proves the baseline -> propose -> measure -> retain mechanics and durable evidence shape. It
does not prove autonomous candidate generation, VM containment, trustworthy real-benchmark
improvement, repeated-run significance, quarantine, or promotion safety.

The same mechanics were then exercised on three existing TerminalBench proxy samples (`tb_01`,
`tb_03`, and `tb_10`). A deliberately minimal command proposer scored `0.55`; corrected commands
proposed from the observed failures scored `1.00`, so the naive loop retained the candidate. On a
three-sample holdout (`tb_04`, `tb_05`, and `tb_07`), both baseline and candidate scored `0.4444`,
so the candidate was rejected there. This is useful proof that the loop works and equally useful
proof that same-sample improvement alone is overfitting, not trustworthy self-improvement.

`maistro_evolve.providers.CodexCliProvider` now supplies the existing Evolve `llm_call` interface
through an authenticated controller-side Codex CLI. It runs each request from a fresh empty
directory with `--sandbox read-only`, sends the prompt over stdin, and returns only Codex's final
message. TerminalBench supports fixed sample subsets so small Codex-backed experiments can be run
before spending a full benchmark budget. Codex credentials remain controller-side and are never
placed inside candidate or benchmark sandboxes.

The provider and TerminalBench integration are covered with a fake Codex executable. A live Codex
call could not be run in the current managed Codex desktop session because Windows denied launching
the installed WindowsApps `codex.exe`, including after an escalation attempt.

### Tougher executable terminal proof

`maistro_evolve.benchmarks.executable_terminal` adds a small objective benchmark that does not
execute unrestricted model-generated shell on the host. Models return a restricted file-operation
plan; the runner executes it in a fresh temporary workspace and checks the exact resulting file
tree and contents.

The current suite contains five training and six holdout tasks covering chained transformations,
cleanup, backup-before-edit, paths with spaces, minimal action budgets, exact-tree enforcement, and
untrusted instructions embedded in file contents. Unsupported shell operations, path escapes,
unexpected files, excess actions, missing responses, and provider failures all fail closed.

A best-effort parent-model dry run scored `5/5` training and `6/6` holdout, showing the tasks and
oracles are solvable. The dedicated `gpt-5.4-mini` provider stopped returning content after a larger
structured batch, then a replacement provider hit its Codex usage limit. A live
`CodexCliProvider` attempt also failed closed because this managed Windows session cannot launch the
installed CLI. Therefore no smaller-model executable score or evolution claim is recorded yet.

### Installed autonomous campaign runner - June 12, 2026

`maistro_rsi.campaign.AutonomousCampaign` is the approved new orchestration path. It is
target-agnostic and installed by the default Maistro workspace. The unified `maistro rsi` and
standalone `maistro-rsi` commands start, resume, and inspect campaigns.

The controller pins the configured base ref (default `develop`) once, then persists only the base
commit, accepted cumulative patch, candidate patches, measurements, events, provider health, and
Evolve strategy guidance. Baseline, proposal, and candidate evaluation use fresh
`IsolatedBuilderSandbox` workspaces. The model's proposal capability is limited to fixed file list,
read, write, delete, and search operations. It cannot execute candidate code or access `.git`;
Maistro exports the patch before candidate code runs in a separate fresh offline evaluation VM.

Fixed tests must pass. A configured real benchmark command must print a final
`{"fidelity":"real","score":...}` JSON line. Protected test/benchmark/workflow paths are rejected
before evaluation. Accepted candidates become experimental incumbents only, and every trial event
records `promotion_eligible: false`. Evolve uses prior rejection evidence to revise a durable
candidate strategy without changing the immutable capability boundary.

Focused contracts cover fresh workspaces, pinned replay, accepted/rejected incumbent handling,
protected paths, durable provider outage/resume, model tool restrictions, evolved strategy
persistence, VM-tier enforcement, and in-sandbox Git runtime verification. No live Docker Sandboxes
or Kata campaign has run on this host. The accepted target official backend is Docker Sandboxes, but
the current code path remains Kata-only until SPEC-190 is implemented. VM conformance, signed/pinned
builder images, external quarantine/promotion, and official real benchmark harness packaging remain
deployment prerequisites.
