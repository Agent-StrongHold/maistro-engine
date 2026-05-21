from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from .types import PipelineGenome


class PopulationStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._store: dict[str, PipelineGenome] = {}
        self._db_path = Optional[str]
        if db_path is not None:
            self._db_path = str(db_path)
            self._init_db()
        else:
            self._db_path = None

    def _init_db(self) -> None:
        assert self._db_path is not None
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS genomes (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

    def _persist(self, genome: PipelineGenome) -> None:
        if self._db_path is None:
            return
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            "INSERT OR REPLACE INTO genomes (id, data) VALUES (?, ?)",
            (genome.id, genome.model_dump_json()),
        )
        conn.commit()
        conn.close()

    def _delete(self, genome_id: str) -> None:
        if self._db_path is None:
            return
        conn = sqlite3.connect(self._db_path)
        conn.execute("DELETE FROM genomes WHERE id = ?", (genome_id,))
        conn.commit()
        conn.close()

    def add(self, genome: PipelineGenome) -> None:
        self._store[genome.id] = genome
        self._persist(genome)

    def get(self, genome_id: str) -> PipelineGenome | None:
        if genome_id in self._store:
            return self._store[genome_id]
        if self._db_path is not None:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT data FROM genomes WHERE id = ?", (genome_id,)
            ).fetchone()
            conn.close()
            if row is not None:
                genome = PipelineGenome.model_validate_json(row[0])
                self._store[genome_id] = genome
                return genome
        return None

    def list_all(self) -> list[PipelineGenome]:
        if self._db_path is not None:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute("SELECT data FROM genomes").fetchall()
            conn.close()
            return [PipelineGenome.model_validate_json(r[0]) for r in rows]
        return list(self._store.values())

    def remove(self, genome_id: str) -> None:
        self._store.pop(genome_id, None)
        self._delete(genome_id)

    def get_champion(self) -> PipelineGenome | None:
        all_genomes = self.list_all()
        scored = [g for g in all_genomes if g.fitness_score is not None]
        if not scored:
            return None
        return max(scored, key=lambda g: g.fitness_score)

    def get_lineage(self, genome_id: str) -> list[PipelineGenome]:
        chain: list[PipelineGenome] = []
        current = self.get(genome_id)
        while current is not None:
            chain.append(current)
            parent_id = current.parent_a_id
            if parent_id is None:
                break
            current = self.get(parent_id)
        return chain

    def cull_bottom(self, pct: float) -> int:
        all_genomes = self.list_all()
        scored = [g for g in all_genomes if g.fitness_score is not None]
        if not scored:
            return 0
        scored.sort(key=lambda g: g.fitness_score)
        cutoff = max(1, int(len(scored) * pct))
        to_remove = scored[:cutoff]
        for g in to_remove:
            self.remove(g.id)
        return len(to_remove)

    def get_breeding_pool(self, top_n: int) -> list[PipelineGenome]:
        all_genomes = self.list_all()
        scored = [g for g in all_genomes if g.fitness_score is not None]
        scored.sort(key=lambda g: g.fitness_score, reverse=True)
        return scored[:top_n]
