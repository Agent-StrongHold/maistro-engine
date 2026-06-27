from __future__ import annotations

import sqlite3
from pathlib import Path

from .audit import GenomeAuditTrail
from .types import PipelineGenome


def _fitness_key(genome: PipelineGenome) -> float:
    score = genome.fitness_score
    assert score is not None
    return score


class PopulationStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._store: dict[str, PipelineGenome] = {}
        self._db_path: str | None
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
            row = conn.execute("SELECT data FROM genomes WHERE id = ?", (genome_id,)).fetchone()
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
        return max(scored, key=_fitness_key)

    def promote(self, genome_id: str) -> PipelineGenome:
        """Promote a tournament-winning genome to live traffic.

        Fail closed: a genome that has not been explicitly marked
        ``approved_for_promotion`` (a human-approval gate — see
        ``human.approve_draft``/``human.delegate_to_role`` graph nodes,
        which the caller is responsible for routing through before calling
        this) is never promoted, no matter how high its fitness/tournament
        score. Winning sandbox evaluation is necessary but not sufficient.
        """
        genome = self.get(genome_id)
        if genome is None:
            raise ValueError(f"unknown genome_id: {genome_id}")
        if not genome.approved_for_promotion:
            raise PermissionError(
                f"genome {genome_id} has not been approved for promotion "
                "(approved_for_promotion=False) — tournament/fitness wins "
                "only qualify a genome for sandbox evaluation, not live traffic"
            )
        previous = self.get_active()
        if previous is not None and previous.id != genome_id:
            previous.is_active = False
            self.add(previous)
        genome.is_active = True
        genome.rollback_target_id = previous.id if previous is not None else None
        self.add(genome)
        return genome

    def get_active(self) -> PipelineGenome | None:
        for g in self.list_all():
            if g.is_active:
                return g
        return None

    def rollback(self) -> PipelineGenome | None:
        """Roll back the currently active (promoted) genome to its predecessor.

        Returns the genome that is active after rollback (the previous
        promotion target), or ``None`` if there was nothing to roll back to.
        The regressing genome is deactivated but not deleted, so it remains
        inspectable.
        """
        active = self.get_active()
        if active is None or active.rollback_target_id is None:
            return None
        target = self.get(active.rollback_target_id)
        if target is None:
            return None
        active.is_active = False
        self.add(active)
        target.is_active = True
        self.add(target)
        return target

    async def promote_audited(self, genome_id: str, audit: GenomeAuditTrail) -> PipelineGenome:
        """Promote, with a mandatory audit record preceding the state change.

        The audit entry is recorded for the *attempt* before ``promote()``
        runs, and a second entry confirms the *commit* after it succeeds. If
        the audit sink itself fails (e.g. the formal-conformance adversarial
        case), the exception propagates before any state mutation happens —
        fail-closed, mirroring ``promote()``'s own approval-gate posture.
        There is no other entrypoint that can flip ``is_active``/promote a
        genome without going through this method or ``promote()`` directly
        (which callers are expected to route through this wrapper for any
        promotion that must be auditable).
        """
        await audit.record("promotion_attempt", genome_id)
        genome = self.promote(genome_id)
        await audit.record("promotion_committed", genome_id)
        return genome

    async def rollback_audited(self, audit: GenomeAuditTrail) -> PipelineGenome | None:
        """Roll back, with a mandatory audit record preceding the state change.

        Logs the attempt (tagged with the currently-active genome, if any)
        before mutating state, then logs the commit (tagged with the
        restored genome, or "none" if there was nothing to roll back to).
        """
        before = self.get_active()
        await audit.record("rollback_attempt", before.id if before is not None else "")
        target = self.rollback()
        await audit.record("rollback_committed", target.id if target is not None else "")
        return target

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
        scored.sort(key=_fitness_key)
        cutoff = max(1, int(len(scored) * pct))
        to_remove = scored[:cutoff]
        for g in to_remove:
            self.remove(g.id)
        return len(to_remove)

    def get_breeding_pool(self, top_n: int) -> list[PipelineGenome]:
        all_genomes = self.list_all()
        scored = [g for g in all_genomes if g.fitness_score is not None]
        scored.sort(key=_fitness_key, reverse=True)
        return scored[:top_n]
