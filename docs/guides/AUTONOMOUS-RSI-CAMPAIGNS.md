# Autonomous RSI and Evolve Campaigns

**Status:** Experimental installed capability  
**Default branch:** `develop`  
**Promotion:** Never autonomous

Maistro installations include a target-agnostic autonomous campaign runner. It can improve any
approved public HTTPS Git repository whose dependencies and fixed evaluation commands are available
inside a configured Builders sandbox image. The target repository does not need Maistro-specific
code.

The runner is available through either installed command:

```text
maistro rsi start ...
maistro-rsi start ...
```

## Security Boundary

- The controller-side model receives only fixed file inspection and mutation capabilities:
  `list_files`, `read_file`, `write_file`, `delete_file`, and `search`.
- The model cannot execute candidate code, access `.git`, receive credentials, push, or open a PR.
- Maistro exports the candidate patch before any candidate-controlled code executes.
- Baseline, proposal, and candidate evaluation each use fresh VM-grade Builders workspaces.
- Repository materialization happens in a temporary networked VM. Proposal and evaluation run in
  separate network-disabled VMs.
- Candidate patches touching protected test, benchmark, workflow, or other operator-configured paths
  are rejected before evaluation.
- Candidate test and benchmark commands execute only in the fresh offline candidate evaluation VM.
- An accepted candidate becomes only the next experimental incumbent. Campaign events always record
  `promotion_eligible: false`.

The controller persists the pinned base commit, accepted cumulative patch, candidate patches,
measurements, events, provider failures, and evolved strategy guidance. Resume reconstructs fresh
workspaces from the pinned commit plus accepted patch; it never resumes a long-lived sandbox.

## Start A Campaign

```text
maistro rsi start \
  --repo-url https://github.com/example/project \
  --base-ref develop \
  --objective "Improve parser correctness without increasing latency" \
  --test-command "python -m pytest -q" \
  --benchmark-command "python tools/real_benchmark.py" \
  --protected-path tests \
  --protected-path tools/real_benchmark.py \
  --sandbox-image example-project-builders:locked \
  --max-iterations 20
```

The benchmark command must exit zero and print a final JSON line:

```json
{"fidelity":"real","score":0.73}
```

Only a higher real-fidelity score can win a benchmark comparison. Missing, malformed, proxy, or stub
score output fails closed. A passing fixed test command is always required.

Use a target-specific sandbox image containing the repository's test dependencies. Every image must
also contain a functioning Git runtime. Campaign initialization records the runtime's reported Git
version and fails if Git is unavailable.

## Resume And Inspect

```text
maistro rsi status CAMPAIGN_ID
maistro rsi stop CAMPAIGN_ID
maistro rsi resume CAMPAIGN_ID
```

State is stored under `MAISTRO_RSI_STATE_DIR`, then `MAISTRO_STATE_DIR/rsi`, or the platform-native
Maistro state directory. Provider outages and infrastructure/evaluation failures are durable and can
be retried with `resume`.
`stop` is a durable kill switch checked between trials; `resume` clears it.

After a rejected trial, Evolve revises and persists the candidate-generation strategy using the
objective evidence. The capability boundary and protected paths are immutable; evolved guidance
cannot grant itself additional tools.

## Current Deployment Prerequisites And Limits

- The current runner requires an available VM-grade backend and fails closed instead of falling back
  to a shared-kernel container. The accepted target official backend is Docker Sandboxes, but its
  adapter is not implemented yet; the current code path still uses Kata.
- The current controller provider is an installed and authenticated Codex CLI.
- Only credential-free public HTTPS repositories on approved hosts are supported.
- The builder image and Git package are not yet pinned, signed, or backed by an SBOM. Operators must
  provide and lock an appropriate image before treating results as reproducible.
- No live Docker Sandboxes or Kata host conformance/escape test has passed in the current development
  environment.
- The legacy `RsiCycle` and Docker-named-as-microVM path still exist for compatibility/tests and are
  not the approved autonomous campaign path.
- Real benchmark evidence can retain an experimental incumbent, but publication still requires
  external quarantine, review, and explicit approval.
