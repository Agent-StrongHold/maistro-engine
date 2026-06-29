# Initial Code Quality Scan — 2026-06-21

This is an initial automated scan against the [Code Quality Evaluation Framework](code-quality-evaluation.md), not a full manual audit and not a claim that the codebase has been equalized for quality. It intentionally excludes security findings because security is reviewed separately.

## Executive summary

Overall status: **baseline scan is now executable for lint, tests, typecheck, radon, and vulture in this environment; radon/vulture currently run as advisory scanners because they report existing findings**.

- **Strongest signal:** `./scripts/run-quality-scans.sh` completes end-to-end: ruff, pytest, and mypy pass; radon and vulture execute and report advisory findings.
- **Test-suite scan fixed:** empty package marker files were removed from per-package test roots, a repository-level fallback async pytest hook was added for scan environments without `pytest-asyncio`, and optional external dependencies are skipped when unavailable.
- **Scanner installation completed:** `./scripts/install-quality-scanners.sh` installed radon 6.0.1 and vulture 2.16 in this environment.
- **Passing deterministic gates:** `./scripts/run-quality-scans.sh` now runs ruff, pytest, mypy, radon, and vulture; radon/vulture findings are advisory until baselines are triaged.
- **Test-fidelity concern:** the repository has many tests, but marker adoption and assertion strength are uneven; `rg` found 251 `assert ... is not None` occurrences in test files and only 74 `scope` and 74 `contract` markers across 299 test files.

## Scope and limitations

This scan is intentionally limited to commands and repository searches that could be run in this environment. It did **not** manually inspect every source file, run mutation testing, run external LLM judges, or fix assertion-strength/marker-adoption/radon/vulture findings.

## Commands run

| Check | Command | Result |
|-------|---------|--------|
| Consolidated scan script | `./scripts/run-quality-scans.sh` | **Pass with advisory findings**: ruff, pytest, and mypy pass; radon and vulture execute; vulture reports findings/status 3 and is treated as advisory. |
| Ruff lint/complexity | `ruff check .` | **Pass**: all checks passed. |
| Pytest full suite | `PYTHONPATH=... pytest -q --import-mode=importlib` via `./scripts/run-quality-scans.sh` | **Pass**: 3140 passed, 12 skipped, 1 xfailed, 31 warnings. |
| Mypy strict typecheck | `PYTHONPATH=.venv/lib/python3.13/site-packages mypy packages/maistro-core/src packages/maistro-server/src packages/maistro-turing/src packages/maistro-canvas/src packages/maistro-bootstrap/src packages/maistro-registry/src` via `./scripts/run-quality-scans.sh` | **Pass**: no issues in 469 source files. |
| Radon scan | `./scripts/run-quality-scans.sh` optional radon step | **Runs advisory**: reports C/D/E complexity findings to triage. |
| Vulture scan | `./scripts/run-quality-scans.sh` optional vulture step | **Runs advisory**: reports unused-code findings and exits status 3; the script records this as advisory instead of failing the already-green deterministic gates. |
| Test marker count | `rg -n "@pytest\.mark\.scope" packages tests -g 'test*.py' \\| wc -l` and `rg -n "@pytest\.mark\.contract" packages tests -g 'test*.py' \\| wc -l` | **Weak adoption**: 74 scope markers and 74 contract markers. |
| Weak assertion count | `rg -n "assert .+ is not None" packages tests -g 'test*.py' \\| wc -l` | **Review needed**: 251 occurrences. |
| Test file count | `rg --files packages tests -g 'test*.py' \\| wc -l` | 299 test files. |

## 20-dimension initial rating

| # | Dimension | Rating | Evidence and notes |
|---|-----------|--------|--------------------|
| 1 | Assertion strength | **Medium-low** | There are many concrete assertions, but 251 `assert ... is not None` occurrences need triage because they can become existence-only terminal checks. |
| 2 | Assertion soundness | **Medium** | The suite now executes in this environment, but weak terminal assertions and real-time sleeps/time calls still make false confidence possible. |
| 3 | Assertion-purpose link | **Medium** | Marker taxonomy exists, but adoption is incomplete: 74 `contract` markers across 299 test files means many tests lack explicit contract linkage. |
| 4 | Edge-case coverage | **Medium** | Boundary and failure tests execute, but time/concurrency-heavy tests still rely on wall-clock calls and sleeps. |
| 5 | Unit-test behavior | **Good scan signal** | The full pytest command now executes successfully in this environment, with optional dependency tests skipped when their tools are absent. |
| 6 | Integration behavior | **Medium** | Integration-style tests run, but some external-tool paths are skipped when tools such as `age`/`age-keygen`, `bip_utils`, or `aiosqlite` are unavailable. |
| 7 | End-to-end behavior | **Medium-low** | The global suite runs, but marker adoption is still incomplete, so e2e confidence is hard to isolate by marker. |
| 8 | Cyclomatic complexity | **Good by ruff / unverified by radon** | Ruff passes with `C90` selected and mccabe max complexity set to 10. Radon is unavailable, so maintainability index and raw complexity trends are not measured. |
| 9 | Self-documenting code | **Medium** | Ruff/import style is clean, but maintainability still depends on resolving strict typing and scanner gaps before deeper claims can be made. |
| 10 | Maintainability | **Medium-low** | Existing docs identify singleton/reset patterns and cross-package issues; current tests reset private globals in conftests, which is a maintainability smell even when necessary. |
| 11 | Docstring coverage | **Unknown** | No docstring coverage tool is configured or available in the active environment. |
| 12 | Dead-code detection | **Advisory findings** | Vulture now runs and reports unused-code findings that require triage and allowlisting before this can become a blocking gate. |
| 13 | Complexity metrics | **Advisory findings** | Ruff mccabe gate passes; radon now runs and reports C/D/E complexity findings that need a baseline before blocking. |
| 14 | Static linting | **Good** | `ruff check .` passes through the consolidated scan script. |
| 15 | Type safety | **Good scan signal** | Mypy passes for 469 source files through the scan script with the local site-packages path exposed. |
| 16 | Dependency hygiene | **Medium** | Mypy import resolution is fixed for the scan script; deptry/import-linter are still not configured as gates. |
| 17 | Duplicate-code detection | **Unknown** | No duplicate-code scanner was run; radon/vulture are now installed but do not replace a duplicate-code checker. |
| 18 | Test quality mutation signal | **Unknown** | Cosmic Ray is listed as a dev dependency, but no mutation run was performed; mutation testing should wait until pytest collection is fixed. |
| 19 | LLM prioritized improvements | **Not run** | The prompt template is available, but no external LLM judging artifact was generated in this evaluation. |
| 20 | LLM worst-flaw review | **Not run** | The prompt template is available, but no external LLM judging artifact was generated in this evaluation. |

## Five prioritized improvements from this scan

1. **Baseline radon and vulture findings.** Radon and vulture now run; the next step is to triage findings, add allowlists for intentional public/dynamic API surfaces, and decide thresholds for blocking gates.
2. **Move scan-script behavior into CI.** `./scripts/run-quality-scans.sh` now works locally in this environment; CI should run it or an equivalent fully synced command.
3. **Reduce optional dependency skips.** Provide `bip_utils`, `aiosqlite`, and `age`/`age-keygen` in the scan image when those contracts should be mandatory rather than skipped.
4. **Ratchet marker adoption.** The repository defines `contract` and `scope` markers, but only 74 of each were found across 299 test files. Start with changed packages and require every new/modified test module to carry scope and contract intent.
5. **Triage weak assertions.** Review the 251 `assert ... is not None` hits and convert terminal existence checks into value, state-transition, event, or error-contract assertions where possible.

## Five biggest flaws visible from this scan

1. **Scanner findings are not yet baselined.** Radon and vulture now execute, but their findings are advisory until the team triages expected dynamic/public API surfaces and sets thresholds.
2. **Some integration contracts are skipped when optional tools are absent.** The suite passes, but optional dependency skips mean identity, SQLite async, and age-encryption paths need a fuller CI image for mandatory coverage.
3. **Scan command portability was fragile.** The new script works around minimal environments by setting `PYTHONPATH`, using importlib import mode, and falling back when pytest/mypy are installed outside the uv environment.
4. **Contract/scope taxonomy is underused.** Without consistent markers, the suite cannot reliably answer whether a change is covered by unit, integration, e2e, behavioral, boundary, or cross-service tests.
5. **Assertion-strength debt is high.** Existence assertions can be useful as intermediate guards, but the current volume demands review to ensure terminal checks prove behavior rather than object creation.

## Suggested next command sequence after remediation

```bash
./scripts/run-quality-scans.sh
```
