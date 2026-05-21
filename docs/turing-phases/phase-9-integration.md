# Phase 9: Integration & Cleanup

**Goal:** Final integration — standalone boot, dependency verification, public API
exports, documentation updates, ADR for migration decisions.

**Depends on:** Phases 2–8 all complete.

---

## 1. Source Inventory

No new source code to port. This phase is integration, packaging, and documentation.

| Task | Lines | Description |
|------|-------|-------------|
| `__main__.py` | ~30 | CLI entry point (`python -m maistro_turing`) |
| `bootstrap_cli.py` | ~100 | Bootstrap CLI command |
| Schema migrations | ~50 | Migration scripts if needed |
| `__init__.py` exports | ~150 | Public API re-exports |
| `pyproject.toml` updates | ~20 | Dependency verification |
| **Total** | **~350** | |

| Source test file | Lines | Key ACs covered |
|-----------------|-------|----------------|
| `tests/test_standalone_boot.py` | ~80 | AC-61.* |
| `tests/test_public_api.py` | ~60 | AC-63.* |
| `tests/test_no_stronghold_imports.py` | ~20 | AC-64.* |
| `tests/test_dependency_completeness.py` | ~30 | AC-62.* |
| Existing integration tests | ~200 | AC-65.* |
| **Total** | **~390** | |

## 2. Target File Mapping

| Task | Target |
|------|--------|
| `__main__.py` | `maistro_turing/__main__.py` |
| `bootstrap_cli.py` | `maistro_turing/cli.py` |
| Schema migration | `maistro_turing/schema/migrations/` |
| Public exports | `maistro_turing/__init__.py` (update) |
| Dependencies | `packages/maistro-turing/pyproject.toml` (update) |

## 3. Acceptance Criteria

### AC-61: Standalone boot (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-61.1 | behavioral | `python -m maistro_turing --config config.yaml --smoke` | Exits with code 0 | Standalone boot + smoke |
| AC-61.2 | behavioral | `python -m maistro_turing --config config.yaml` | Enters reactor loop, processes ticks | Runtime loop |
| AC-61.3 | behavioral | `python -m maistro_turing --help` | Prints usage and exits 0 | Help text |
| AC-61.4 | behavioral | `python -m maistro_turing` without config | Prints error, exits 1 | Missing config error |
| AC-61.5 | behavioral | `python -m maistro_turing --bootstrap` | Runs personality bootstrap interactively | Bootstrap CLI |

### AC-62: Dependency completeness (boundary)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-62.1 | boundary | `pip install -e packages/maistro-turing` | Succeeds, no missing deps | Install works |
| AC-62.2 | boundary | `pyproject.toml` lists `maistro-core>=0.1.0` as dependency | maistro-core is listed | Core dependency |
| AC-62.3 | boundary | All runtime imports resolve | No ImportError on import maistro_turing | Import completeness |
| AC-62.4 | boundary | Only pip deps are `httpx`, `PyYAML`, `maistro-core` | No unlisted deps | Deps listed |

### AC-63: Public API exports (boundary)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-63.1 | boundary | `from maistro_turing import EpisodicMemory, MemoryTier, ...` | All public types importable | Public API complete |
| AC-63.2 | boundary | `from maistro_turing import Repo, SelfRepo` | Core repos importable | Repo access |
| AC-63.3 | boundary | `from maistro_turing import Motivation, Dreamer, ...` | Cognition types importable | Cognition access |
| AC-63.4 | boundary | `from maistro_turing import FakeProvider, ToolRegistry` | Infrastructure importable | Infra access |
| AC-63.5 | boundary | `maistro_turing.__all__` | Contains all public names | __all__ is complete |

### AC-64: No stronghold imports (boundary)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-64.1 | boundary | `grep -r "stronghold" packages/maistro-turing/` | Returns nothing | No stronghold refs |
| AC-64.2 | boundary | `grep -r "from stronghold" packages/maistro-turing/` | Returns nothing | No stronghold imports |
| AC-64.3 | boundary | `grep -r "import stronghold" packages/maistro-turing/` | Returns nothing | No stronghold imports |

### AC-65: Documentation + ADR updates (boundary)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-65.1 | boundary | `CLAUDE.md` updated with maistro-turing test commands | Commands present | CLAUDE.md updated |
| AC-65.2 | boundary | Migration ADR written in `docs/adr/` | ADR file exists | ADR written |
| AC-65.3 | boundary | `TURING-MIGRATION-SPEC.md` status changed from Draft to Complete | Status is Complete | Spec complete |
| AC-65.4 | boundary | AgentTuring repo README updated to point to maistro-turing | README updated | Pointer added |

## 4. Unit Test Plan

| Test file | ACs covered | Marks |
|-----------|-------------|-------|
| `tests/test_standalone_boot.py` | AC-61.1..61.5 | `contract("behavioral")` `scope("e2e")` |
| `tests/test_public_api.py` | AC-63.1..63.5 | `contract("boundary")` `scope("unit")` |
| `tests/test_no_stronghold_imports.py` | AC-64.1..64.3 | `contract("boundary")` `scope("unit")` |
| `tests/test_dependency_completeness.py` | AC-62.1..62.4 | `contract("boundary")` `scope("unit")` |

### Test: Standalone boot

```python
import subprocess
import pytest

@pytest.mark.contract("behavioral")
@pytest.mark.scope("e2e")
def test_standalone_smoke(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("db_path: ':memory:'\nprovider: fake\n")
    result = subprocess.run(
        ["python", "-m", "maistro_turing", "--config", str(config), "--smoke"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"smoke failed: {result.stderr}"
```

### Test: No stronghold imports

```python
import subprocess
import pytest

@pytest.mark.contract("boundary")
@pytest.mark.scope("unit")
def test_no_stronghold_imports():
    result = subprocess.run(
        ["grep", "-r", "stronghold", "packages/maistro-turing/src/"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, f"Found stronghold refs: {result.stdout}"
```

### Test: Public API completeness

```python
import pytest

@pytest.mark.contract("boundary")
@pytest.mark.scope("unit")
def test_public_api_imports():
    from maistro_turing import (
        EpisodicMemory, MemoryTier, SourceKind, MemoryRepo, WorkingMemoryStore,
        Repo, SelfRepo, Motivation, Dreamer, FakeReactor, FakeProvider,
        ToolRegistry, Mood, HEXACO_FACETS,
    )
    assert EpisodicMemory is not None
    assert MemoryTier.OBSERVATION is not None
```

## 5. Phase Gate

- [ ] All AC-61..65 tests pass
- [ ] `ruff check packages/maistro-turing/` clean
- [ ] `mypy packages/maistro-turing/ --strict` clean
- [ ] Test count >= 370 (matching source test count)
- [ ] No `stronghold` imports
- [ ] `python -m maistro_turing --smoke` exits 0
- [ ] `pip install -e packages/maistro-turing` succeeds
- [ ] `python -c "import maistro_turing; print('OK')"` succeeds
- [ ] CLAUDE.md updated with maistro-turing commands
- [ ] Migration ADR written
- [ ] TURING-MIGRATION-SPEC.md status = Complete

## 6. Post-Phase Checklist (acceptance criteria from migration spec)

Per `docs/TURING-MIGRATION-SPEC.md` section 8:

1. [ ] **All 370+ tests pass** under `packages/maistro-turing/tests/`
2. [ ] **`ruff check` + `mypy --strict`** pass clean on all `maistro-turing` code
3. [ ] **`python -m maistro_turing`** boots with a config file and enters the reactor loop
4. [ ] **Chat works:** send a message, get a response, memory is stored
5. [ ] **Dreaming works:** after enough memories, consolidation runs and produces WISDOM-tier memories
6. [ ] **No stronghold imports:** `grep -r "stronghold" packages/maistro-turing/` returns nothing
7. [ ] **`pip install maistro-turing`** works standalone (with maistro-core)
8. [ ] **Coverage >= 80%** on all ported modules
