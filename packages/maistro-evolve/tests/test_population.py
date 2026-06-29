from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from maistro_evolve.population import PopulationStore
from maistro_evolve.types import DAGTopology, EvalWeights, NodeGenome, PipelineGenome


def _genome(
    genome_id: str,
    fitness_score: float | None = None,
    parent_a_id: str | None = None,
) -> PipelineGenome:
    return PipelineGenome(
        id=genome_id,
        name=genome_id,
        topology=DAGTopology(
            nodes=[
                NodeGenome(
                    id="q1",
                    role="queen",
                    strategy="react",
                    model="gpt-4",
                    temperature=0.3,
                    max_tokens=4096,
                    system_prompt="test",
                    max_tool_rounds=5,
                )
            ],
            edges=[],
            entry_node="q1",
            max_cycles=3,
            beam_width=1,
            use_scout=False,
        ),
        eval_weights=EvalWeights(),
        fitness_score=fitness_score,
        parent_a_id=parent_a_id,
        created_at=datetime.now(UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
    )


@pytest.fixture(params=["memory", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> PopulationStore:
    if request.param == "memory":
        return PopulationStore()
    return PopulationStore(tmp_path / "pop.db")


def test_add_and_get_roundtrip(store: PopulationStore) -> None:
    genome = _genome("g1", fitness_score=0.5)
    store.add(genome)
    assert store.get("g1") == genome


def test_get_missing_returns_none(store: PopulationStore) -> None:
    assert store.get("missing") is None


def test_list_all_returns_every_added_genome(store: PopulationStore) -> None:
    store.add(_genome("g1"))
    store.add(_genome("g2"))
    ids = {g.id for g in store.list_all()}
    assert ids == {"g1", "g2"}


def test_remove_deletes_genome(store: PopulationStore) -> None:
    store.add(_genome("g1"))
    store.remove("g1")
    assert store.get("g1") is None
    assert store.list_all() == []


def test_get_champion_returns_none_when_no_scored_genomes(store: PopulationStore) -> None:
    store.add(_genome("g1", fitness_score=None))
    assert store.get_champion() is None


def test_get_champion_returns_highest_scoring_genome(store: PopulationStore) -> None:
    store.add(_genome("low", fitness_score=0.2))
    store.add(_genome("high", fitness_score=0.9))
    store.add(_genome("unscored", fitness_score=None))
    champion = store.get_champion()
    assert champion is not None
    assert champion.id == "high"


def test_get_lineage_walks_parent_a_chain(store: PopulationStore) -> None:
    store.add(_genome("grandparent"))
    store.add(_genome("parent", parent_a_id="grandparent"))
    store.add(_genome("child", parent_a_id="parent"))

    lineage = store.get_lineage("child")

    assert [g.id for g in lineage] == ["child", "parent", "grandparent"]


def test_get_lineage_stops_when_parent_id_missing_from_store(store: PopulationStore) -> None:
    store.add(_genome("orphan", parent_a_id="never-added"))
    lineage = store.get_lineage("orphan")
    assert [g.id for g in lineage] == ["orphan"]


def test_get_lineage_for_unknown_genome_returns_empty(store: PopulationStore) -> None:
    assert store.get_lineage("nope") == []


def test_cull_bottom_returns_zero_when_no_scored_genomes(store: PopulationStore) -> None:
    store.add(_genome("g1", fitness_score=None))
    assert store.cull_bottom(0.5) == 0
    assert store.get("g1") is not None


def test_cull_bottom_removes_lowest_scoring_fraction(store: PopulationStore) -> None:
    for i, score in enumerate([0.1, 0.2, 0.3, 0.4, 0.9]):
        store.add(_genome(f"g{i}", fitness_score=score))

    removed = store.cull_bottom(0.4)

    assert removed == 2
    remaining_ids = {g.id for g in store.list_all()}
    assert "g0" not in remaining_ids
    assert "g1" not in remaining_ids
    assert "g4" in remaining_ids


def test_cull_bottom_always_removes_at_least_one(store: PopulationStore) -> None:
    store.add(_genome("only", fitness_score=0.5))
    removed = store.cull_bottom(0.01)
    assert removed == 1
    assert store.list_all() == []


def test_get_breeding_pool_returns_top_n_scored_descending(store: PopulationStore) -> None:
    store.add(_genome("low", fitness_score=0.1))
    store.add(_genome("mid", fitness_score=0.5))
    store.add(_genome("high", fitness_score=0.9))
    store.add(_genome("unscored", fitness_score=None))

    pool = store.get_breeding_pool(top_n=2)

    assert [g.id for g in pool] == ["high", "mid"]


def test_get_breeding_pool_empty_when_no_scored_genomes(store: PopulationStore) -> None:
    store.add(_genome("g1", fitness_score=None))
    assert store.get_breeding_pool(top_n=5) == []


def test_sqlite_store_persists_across_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "pop.db"
    store1 = PopulationStore(db_path)
    store1.add(_genome("g1", fitness_score=0.7))

    store2 = PopulationStore(db_path)
    assert store2.get("g1") is not None
    assert store2.get("g1").fitness_score == 0.7  # type: ignore[union-attr]


def test_sqlite_store_get_caches_in_memory_after_first_load(tmp_path: Path) -> None:
    db_path = tmp_path / "pop.db"
    store1 = PopulationStore(db_path)
    store1.add(_genome("g1"))

    store2 = PopulationStore(db_path)
    first = store2.get("g1")
    assert first is not None
    # second get hits the in-memory cache populated by the first lookup.
    assert store2.get("g1") is first
