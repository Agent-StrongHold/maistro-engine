# Code quality gates

What actually runs, and what each gate will and will not stop. Every entry here
is a step in [`.github/workflows/quality.yml`](../.github/workflows/quality.yml)
or [`ci.yml`](../.github/workflows/ci.yml) — if a rule is not in this file, it is
not enforced, and a rule that is enforced is enforced on every pull request
against `main`, `integration`, and `develop`.

This replaces the June-2026 audit documents (`quality-standards.md`,
`claude-quality-enforcement.md`, and the three dated `code-quality-*` scans).
Those were point-in-time findings, not standards: every specific defect they
named has since been fixed, and they described the pre-monorepo `src/maistro/`
layout. Their durable content is the gates below, which run rather than
describe. Provenance remains in git history.

## Ratchets vs. floors

Two different shapes, and the difference matters when you are deciding whether
a change is allowed to make a number worse.

A **ratchet** records the currently-tolerated set in a checked-in baseline and
fails on anything worse than it. It never auto-grows: widening a baseline is an
edit a reviewer sees. The backlog is worked down over time rather than in one
pull request.

A **floor** is a fixed threshold with no baseline. It does not move with the
code.

A ratchet keyed on a *count* has a known weakness: one fix pays for one new
defect, so the total can stand still while the code churns. Where that matters,
the gate is keyed on *identity* instead — the exact finding, not how many there
are — and then a defect that gets fixed but left in the baseline fails the build
too. That asymmetry is deliberate: retained slack could otherwise pay for a
later regression.

## The gates

| Gate | Shape | Current setting | Stops |
|---|---|---|---|
| `ruff check` (full ruleset) | floor | zero findings | lint violations |
| `ruff format --check` | floor | zero diffs | unformatted code |
| `mypy --strict` | floor | zero errors, all nine `packages/*/src` | type errors |
| pyright | ratchet | 24 | type errors mypy does not catch |
| radon CC | identity ratchet | `quality/radon-baseline.json` | a new or regressed complexity hotspot |
| xenon | count ratchet | 77 | per-function > B, per-module > B, project average > A |
| vulture (count) | count ratchet | 1426, in `quality.yml` | dead code at confidence ≥ 60 |
| vulture (identity) | identity ratchet | count + SHA-256 per rule, in `vulture-ratchet.yml` | the same finding set changing, including a same-count substitution |
| reachability | identity ratchet | `quality/reachability-baseline.json` | a module built but never wired to any entry point |
| coverage | floor | 88% line + branch, publish set | undertested code |
| interrogate | ratchet | 38 / 45 / 63 / 46 per tree | missing docstrings, per-subtree floors |
| suite inventory | identity ratchet | `docs/testing/SUITE-INVENTORY.md` | a suite silently ceasing to collect |
| enumeration coverage | identity ratchet | `scripts/check_enumerations.py` | a derived control list drifting from its source enum |
| doc links | floor | zero broken | a relative markdown link whose target does not exist |
| version consistency | floor | exact match | any version site disagreeing with `VERSION` |
| benchmark provenance | floor | pinned digests | a vendored IFEval/BFCL grader or corpus changing unnoticed |
| architecture fitness | floor | zero violations | a forbidden cross-layer dependency |
| Hypothesis conformance | floor | zero falsifying examples | a property violation in `formal/` |

Vulture is gated twice on purpose. `quality.yml` keeps a cheap total-count
ceiling; `vulture-ratchet.yml` pins each rule's exact finding set by count and
digest, which is what catches a same-count substitution — one finding fixed and
a different one introduced under the same rule, invisible to a count alone.

Security scanning (bandit, semgrep, gitleaks), dependency audit (pip-audit),
container scan/SBOM/cosign, and mutation testing run in their own workflows —
`security.yml` and `mutation.yml`.

## Why a ratchet rather than a clean sweep

Several baselines are large. They are the honest count of a backlog that
predates the gate, and the point of recording them is that the number can only
go down. Lowering one is ordinary work; raising one requires saying so in a
diff.

Two rules follow from that, and they are the ones most often got wrong:

- **Fix at the source, not in the baseline.** A new finding is a reason to
  change the code. Adding it to a baseline is for a finding that is genuinely
  intended — a library-only surface, test scaffolding — and then it wants a
  note saying which.
- **Shrink the baseline in the same pull request as the improvement.** The
  identity-keyed ratchets enforce this; the count-keyed ones cannot, so it is on
  the author.

## Running them locally

The gates are ordinary scripts. Nothing here needs CI:

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy packages/maistro-core/src   # …and the other eight packages/*/src
uv run python scripts/check-radon-baseline.py
uv run python scripts/check-reachability.py
uv run python scripts/check-suite-inventory.py
uv run python scripts/check-doc-links.py
uv run python scripts/bump_version.py --check
uv run python scripts/check-vulture-baseline.py packages/*/src \
  --min-confidence 60 --exclude '*/third_party/*'
```

`scripts/check-suite-inventory.py --update` rewrites the inventory from an
actual collection. Always regenerate it that way — never by adjusting the
number by hand to match a delta, which defeats the point of the gate.
