"""GoldenRecord — versioned research ground truth per persona (SPEC-192 Stage 2).

Research outputs (exemplar sources + vocabulary-mapped criteria) are stored as
versioned records. Re-research never overwrites: a new version supersedes the
previous one, and :func:`diff_records` surfaces added/removed/changed criteria
for human sign-off before the Tier 1 floor is replaced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class SourceEvidence:
    """One fetched exemplar source."""

    url: str
    title: str
    full_text: str
    fetch_ts: datetime


@dataclass(frozen=True)
class EvidencedCriterion:
    """One vocabulary-mapped criterion plus the sources supporting it."""

    name: str
    weight: int
    check: dict[str, Any]  # vocabulary check-spec
    evidence: list[str] = field(default_factory=list)  # supporting source URLs
    needs_review: bool = False  # True when mapped to a `registered` escape hatch


@dataclass(frozen=True)
class GoldenRecord:
    """Versioned golden-truth record for one persona."""

    persona_id: str
    version: int  # increments on re-research
    sources: list[SourceEvidence]
    criteria: list[EvidencedCriterion]
    created_at: datetime
    supersedes: int | None = None  # previous version (never deleted)


@dataclass(frozen=True)
class GoldenRecordDiff:
    """Criteria changes between two GoldenRecord versions (for human sign-off)."""

    persona_id: str
    old_version: int | None
    new_version: int
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)  # same name, different weight/check

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)


def diff_records(old: GoldenRecord | None, new: GoldenRecord) -> GoldenRecordDiff:
    """Diff two golden records by criterion name, weight, and check spec."""
    old_by_name = {c.name: c for c in old.criteria} if old else {}
    new_by_name = {c.name: c for c in new.criteria}
    added = sorted(set(new_by_name) - set(old_by_name))
    removed = sorted(set(old_by_name) - set(new_by_name))
    changed = sorted(
        name
        for name in set(old_by_name) & set(new_by_name)
        if (old_by_name[name].weight, old_by_name[name].check)
        != (new_by_name[name].weight, new_by_name[name].check)
    )
    return GoldenRecordDiff(
        persona_id=new.persona_id,
        old_version=old.version if old else None,
        new_version=new.version,
        added=added,
        removed=removed,
        changed=changed,
    )


@runtime_checkable
class GoldenRecordStore(Protocol):
    """Store protocol for versioned golden records (versions are never deleted)."""

    async def save(
        self,
        persona_id: str,
        sources: list[SourceEvidence],
        criteria: list[EvidencedCriterion],
    ) -> GoldenRecord:
        """Persist a new version superseding (not replacing) the latest one."""
        ...

    async def get_latest(self, persona_id: str) -> GoldenRecord | None: ...

    async def get_version(self, persona_id: str, version: int) -> GoldenRecord | None: ...

    async def list_versions(self, persona_id: str) -> list[int]: ...


class InMemoryGoldenRecordStore:
    """In-memory GoldenRecordStore (P1 reference implementation)."""

    def __init__(self) -> None:
        self._records: dict[str, dict[int, GoldenRecord]] = {}

    async def save(
        self,
        persona_id: str,
        sources: list[SourceEvidence],
        criteria: list[EvidencedCriterion],
    ) -> GoldenRecord:
        versions = self._records.setdefault(persona_id, {})
        latest = max(versions) if versions else None
        record = GoldenRecord(
            persona_id=persona_id,
            version=(latest or 0) + 1,
            sources=list(sources),
            criteria=list(criteria),
            created_at=datetime.now(UTC),
            supersedes=latest,
        )
        versions[record.version] = record
        return record

    async def get_latest(self, persona_id: str) -> GoldenRecord | None:
        versions = self._records.get(persona_id)
        if not versions:
            return None
        return versions[max(versions)]

    async def get_version(self, persona_id: str, version: int) -> GoldenRecord | None:
        return self._records.get(persona_id, {}).get(version)

    async def list_versions(self, persona_id: str) -> list[int]:
        return sorted(self._records.get(persona_id, {}))
