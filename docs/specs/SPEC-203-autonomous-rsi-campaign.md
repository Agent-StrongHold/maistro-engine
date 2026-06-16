# SPEC-203: Installed Autonomous RSI And Evolve Campaign

**Status:** Experimental

Any Maistro installation can run a resumable campaign against an approved public HTTPS repository.
The controller pins the configured base ref, generates candidates through a non-executing proposal
capability, exports each patch before candidate code runs, evaluates baseline and candidate in
separate fresh offline VM-grade Builders workspaces, and persists objective evidence. No campaign
capability can push, open a PR, merge, or promote.

## Acceptance Criteria

| AC | Criterion |
|----|-----------|
| campaign-1 | Initialization pins the configured base ref (default `develop`) and records VM tier, backend, and in-sandbox Git version. |
| campaign-2 | Baseline, proposal, and candidate evaluation use distinct fresh workspaces reconstructed from the pinned base commit plus accepted cumulative patch. |
| campaign-3 | The model-facing proposal view exposes fixed file listing, read, write, delete, and search operations only; it cannot execute code, export a diff, close the VM, or access `.git`. |
| campaign-4 | Maistro exports the proposal patch before executing candidate-controlled code in a separate fresh evaluation workspace. |
| campaign-5 | Candidate patches touching protected paths are rejected before evaluation. |
| campaign-6 | Provider outages and infrastructure failures persist durable states that `resume` can retry. |
| campaign-7 | Rejected candidates never replace the incumbent; accepted candidates persist as cumulative patch artifacts and are always marked ineligible for promotion. |
| campaign-8 | A benchmark win requires a passing fixed test command and a higher final JSON score explicitly labeled `fidelity=real`. |
| campaign-9 | Evolve revises durable candidate strategy from prior rejection evidence while immutable capability and promotion boundaries remain unchanged. |
| campaign-10 | A durable stop request halts the controller between trials, and resume clears it before reconstructing fresh workspaces. |

## Residual Risks

- No live Docker Sandboxes or Kata host conformance/escape test has passed yet.
- The accepted target official backend is Docker Sandboxes, but the current code path still uses
  Kata until the SPEC-190 adapter is implemented.
- Builder/Git images are not yet pinned, signed, or SBOM-backed.
- Real benchmark harness packaging is operator supplied.
- External quarantine, review, and approval are still required before publication.
