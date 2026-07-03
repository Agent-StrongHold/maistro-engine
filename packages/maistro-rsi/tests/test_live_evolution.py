"""Unified live evolution (ADR-070126-6386 v2, "the run IS the gym"): the genome
population is the tournament roster, real work folds back as scores, transient
provider errors bench a model (it sits out — no sample, no death), and model
reliability multiplies into fitness. Stub apply, no LLM/network."""

from __future__ import annotations

import random
import subprocess
from pathlib import Path

from maistro_rsi.local_loop import (
    LocalRsiConfig,
    LocalRsiLoop,
    _is_transient_provider_error,
)
from maistro_rsi.protocols import MicroVmSandbox


def _git(cwd: Path, *args: str) -> None:
    proc = subprocess.run(
        ["git", "-c", "core.longpaths=true", *args], cwd=str(cwd), capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} rc={proc.returncode}: {proc.stderr.strip()}")


def _make_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "rsi@test.local")
    _git(path, "config", "user.name", "RSI Test")
    (path / "value.txt").write_text("0\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return path


def _live_config(tmp_path: Path, **overrides) -> LocalRsiConfig:
    defaults = {
        "repo_path": str(_make_repo(tmp_path / "src")),
        "test_command": "exit 0",
        "work_root": str(tmp_path / "work"),
        "max_cycles": 2,
        "model": "testmodel",
        "genome_db": str(tmp_path / "pop.db"),
        "roster_size": 3,
    }
    defaults.update(overrides)
    return LocalRsiConfig(**defaults)


def _make_apply(writer) -> object:
    async def apply(sandbox: MicroVmSandbox, workspace: str) -> None:
        writer(Path(workspace))

    return apply


def _bump(ws: Path) -> None:
    f = ws / "value.txt"
    f.write_text(f.read_text() + "x\n", encoding="utf-8")


def test_transient_error_classifier() -> None:
    assert _is_transient_provider_error("LiteLLM gateway 429: RateLimitError ...")
    assert _is_transient_provider_error("You exceeded your current quota, check billing")
    assert _is_transient_provider_error("503 service overloaded")
    assert not _is_transient_provider_error("list index out of range")
    assert not _is_transient_provider_error("SyntaxError: invalid syntax")


def test_reliability_ema_decays_and_recovers(tmp_path: Path) -> None:
    random.seed(7)
    loop = LocalRsiLoop(_live_config(tmp_path), apply_patch=_make_apply(_bump))
    assert loop._observe_reliability("m", ok=False) == 0.7
    assert loop._observe_reliability("m", ok=False) == 0.49
    assert loop._observe_reliability("m", ok=True) > 0.49  # recovers on success


def test_real_work_scores_the_population_and_it_evolves(tmp_path: Path) -> None:
    random.seed(11)
    config = _live_config(tmp_path)
    loop = LocalRsiLoop(config, apply_patch=_make_apply(_bump))
    result = loop.run()

    # Work was KEPT (promotions ratcheted) — no separate training evals exist.
    assert result.promotions == 2
    genomes = loop._population.list_all()
    # Real composites folded into the authoring genomes (samples counted).
    sampled = [g for g in genomes if g.harness_params.get("eval_samples", {}).get("code_rsi")]
    assert sampled, "cycle work should have scored the genomes that authored it"
    # Fitness computed with the model-reliability multiplier recorded.
    assert any(g.fitness_score is not None for g in genomes)
    assert any("model_reliability" in g.harness_params for g in genomes)
    # The population persisted (lineage survives runs).
    assert (tmp_path / "pop.db").exists()


def test_transient_provider_error_benches_model_and_folds_nothing(tmp_path: Path) -> None:
    random.seed(13)

    async def rate_limited(sandbox: MicroVmSandbox, workspace: str) -> None:
        raise RuntimeError("LiteLLM gateway 429: RateLimitError - quota exceeded")

    config = _live_config(tmp_path)
    loop = LocalRsiLoop(config, apply_patch=rate_limited)
    result = loop.run()

    # The run survived and completed every cycle.
    assert len(result.cycles) == 2
    # The model got benched instead of the genomes dying.
    assert loop._bench.get("testmodel", 0) > 1
    # Sitting out is NEUTRAL: no samples were folded into any genome.
    for g in loop._population.list_all():
        assert not g.eval_scores, "a benched cycle must not score the genome"
    # But reliability remembers: the model's score decayed below 1.0.
    assert loop._reliability.get("testmodel", 1.0) < 1.0
