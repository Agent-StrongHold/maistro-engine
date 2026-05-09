"""Cross-repo link checker for ADR/spec front-matter.

Every cross-reference of the form `<repo>#<id>` must resolve to an
existing ADR or spec, per `engine#ADR-031`.

The `Resolver` protocol decouples link-checking from the underlying
truth source so tests can use an in-memory fake while production uses
the GitHub API.

Resolvers shipped:

- `FilesystemResolver` — looks at local files for the engine repo;
  used in engine self-check.
- `GitHubResolver` — uses the GitHub Contents API (httpx, already a
  dep) for cross-repo verification. Caches one directory listing per
  repo to minimize API calls.
- `FakeResolver` — in-memory, deterministic; for tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import httpx

from tools.registry.schema import FrontMatter

_RELATIONSHIP_FIELDS: tuple[str, ...] = (
    "substrate",
    "implements",
    "related",
    "supersedes",
    "blocks",
    "blocked_by",
)

# Default repo → owner mapping for the four-repo system.
_DEFAULT_REPO_OWNERS: dict[str, str] = {
    "maistro-engine": "BlakeMatthews-dev",
    "Project_mAIstro": "BlakeMatthews-dev",
    "AgentTuring": "BlakeMatthews-dev",
    "stronghold": "agent-stronghold",
}


class Resolver(Protocol):
    """Resolves whether a `<repo>#<id>` reference points to a real artifact."""

    def resolve(self, repo: str, item_id: str) -> bool: ...


@dataclass(frozen=True)
class LinkResult:
    source: str  # e.g. "maistro-engine#ADR-030"
    field_name: str  # e.g. "substrate"
    target: str  # e.g. "maistro-engine#ADR-019"
    resolved: bool

    def render(self) -> str:
        status = "OK" if self.resolved else "DANGLING"
        return f"{self.source}.{self.field_name} -> {self.target} ({status})"


def check_links(
    front_matters: list[FrontMatter],
    resolver: Resolver,
) -> list[LinkResult]:
    """Check every cross-reference in every front-matter against `resolver`."""
    results: list[LinkResult] = []
    for fm in front_matters:
        source = f"{fm.repo.value}#{fm.id}"
        for field_name in _RELATIONSHIP_FIELDS:
            refs: list[str] = list(getattr(fm, field_name))
            for ref in refs:
                target_repo, target_id = ref.split("#", 1)
                resolved = resolver.resolve(target_repo, target_id)
                results.append(
                    LinkResult(
                        source=source,
                        field_name=field_name,
                        target=ref,
                        resolved=resolved,
                    )
                )
    return results


@dataclass
class FakeResolver:
    """In-memory resolver for tests.

    `known[repo]` is the set of `<id>` strings (e.g. {"ADR-030"})
    that the resolver should consider present.
    """

    known: dict[str, set[str]] = field(default_factory=dict)

    def resolve(self, repo: str, item_id: str) -> bool:
        return item_id in self.known.get(repo, set())


@dataclass
class FilesystemResolver:
    """Resolver that checks local engine filesystem for ADR/spec presence.

    Only authoritative for `maistro-engine`; for any other repo, returns
    ``True`` (optimistic) so a single-repo run doesn't false-flag valid
    cross-repo references. Use `GitHubResolver` for cross-repo accuracy.
    """

    engine_root: Path

    def resolve(self, repo: str, item_id: str) -> bool:
        if repo != "maistro-engine":
            return True  # optimistic; cross-repo check needs GitHubResolver

        adr_dir = self.engine_root / "docs" / "adr"
        if not adr_dir.is_dir():
            return False

        prefix = f"{item_id}-"
        for f in adr_dir.iterdir():
            if f.name.startswith(prefix) and f.suffix == ".md":
                return True
        return False


@dataclass
class GitHubResolver:
    """Resolver using GitHub Contents API to verify cross-repo refs.

    Caches per-repo directory listings (one API call per repo per run).
    Optional auth token reduces rate-limit pressure (5000 req/hr vs 60).
    """

    repo_owners: dict[str, str] = field(
        default_factory=lambda: dict(_DEFAULT_REPO_OWNERS)
    )
    token: str | None = None
    _id_cache: dict[str, set[str]] = field(default_factory=dict)

    def _fetch_ids(self, repo: str) -> set[str]:
        if repo in self._id_cache:
            return self._id_cache[repo]

        owner = self.repo_owners.get(repo)
        if owner is None:
            self._id_cache[repo] = set()
            return set()

        ids: set[str] = set()
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        for path in ("docs/adr", "docs/specs"):
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
            try:
                resp = httpx.get(url, headers=headers, timeout=10)
            except httpx.RequestError:
                continue
            if resp.status_code != 200:
                continue
            payload = resp.json()
            if not isinstance(payload, list):
                continue
            for entry in payload:
                name = entry.get("name", "")
                if not name.endswith(".md"):
                    continue
                stem = name[: -len(".md")]
                # "ADR-030-foo" -> first two hyphen-delimited parts: "ADR-030"
                parts = stem.split("-", 2)
                if len(parts) >= 2:
                    ids.add(f"{parts[0]}-{parts[1]}")

        self._id_cache[repo] = ids
        return ids

    def resolve(self, repo: str, item_id: str) -> bool:
        return item_id in self._fetch_ids(repo)
