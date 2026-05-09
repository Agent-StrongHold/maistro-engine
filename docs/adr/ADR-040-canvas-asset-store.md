---
id: ADR-040
title: Canvas Asset Store — Persistence for ADR-039 Layer Model
repo: maistro-engine
kind: adr
status: Proposed
created: 2026-05-09
substrate:
  - maistro-engine#ADR-039
  - maistro-engine#ADR-005
  - maistro-engine#ADR-031
  - maistro-engine#ADR-032
implements: []
related:
  - maistro-engine#ADR-019
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests:
  - packages/maistro-canvas/tests/test_asset_store.py
layer: Foundation
owners:
  - '@BlakeMatthews-dev'
---

# ADR-040: Canvas Asset Store

## Context

ADR-039 ships the typed scene-graph layer model in `layers.py` but is
explicitly contracts-only — no implementation. Without a persistence
layer the model is unobservable; the agent (davinci) and the future
FastAPI surface have no way to load or save AssetDefinitions, asset
sheets, instances, child profiles, or the book-level WorldStyle.

The existing canvas `store.py` persists `CanvasRecord`, `LayerRecord`,
`GenerationJobRecord`, `CompositeResult`. Those are not the new model:
their `LayerRecord` is the deprecated flat `LayerType` shape, not the
ADR-039 `AssetInstance`.

## Decision

Engine ships **`maistro_canvas.canvas.asset_store`** alongside the
existing `store.py`. Both coexist while the migration from `LayerRecord`
to `AssetInstance` is figured out (a separate ADR). The new module
implements the protocols added in ADR-039:

- `AssetRegistry` — CRUD for `AssetDefinition`s
- `AssetSheetService` — generate/get/regenerate sheets (the actual
  generation backend is wired by the consumer; the store persists
  rows and bumps `revision`)

Plus three new entities the protocols don't cover but the model
requires:

- `AssetInstance` rows — placement of a definition on a canvas, with
  parent_id, parent_socket, transform, slot, anchor, occlusion,
  personalization, skin_binding, prompt_nudge, history.
- `ChildProfile` rows — the personalisation key.
- `Book` rows — the natural container for `WorldStyle` and an ordered
  list of `StyleVolume`s.

### Tables

```sql
-- Named, reusable definitions. Inline (anonymous) definitions live
-- inside the asset_instances row, never here.
CREATE TABLE asset_definitions (
    asset_id            TEXT PRIMARY KEY,
    kind                TEXT NOT NULL,
    base_prompt         TEXT NOT NULL,
    sockets             JSONB NOT NULL DEFAULT '[]',
    skin_set            JSONB,
    default_world_style JSONB,
    pose_geometry       JSONB,
    org_id              TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per asset_id; revision bumps on regenerate.
CREATE TABLE asset_sheets (
    asset_id           TEXT PRIMARY KEY
                       REFERENCES asset_definitions(asset_id)
                       ON DELETE CASCADE,
    refs               JSONB NOT NULL,
    sheet_image        TEXT NOT NULL,
    revision           INTEGER NOT NULL DEFAULT 1,
    generation_params  JSONB NOT NULL DEFAULT '{}',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Placement of a definition on a canvas. Either definition_id (named,
-- registered) OR inline_definition (anonymous, embedded). Exactly one
-- is non-null; enforced by CHECK constraint.
CREATE TABLE asset_instances (
    instance_id        TEXT PRIMARY KEY,
    canvas_id          TEXT NOT NULL,
    definition_id      TEXT REFERENCES asset_definitions(asset_id) ON DELETE RESTRICT,
    inline_definition  JSONB,
    parent_id          TEXT REFERENCES asset_instances(instance_id) ON DELETE SET NULL,
    parent_socket      TEXT,
    transform          JSONB NOT NULL DEFAULT '{}',
    slot               JSONB,
    anchor             TEXT,
    occlusion          JSONB NOT NULL DEFAULT '{"in_front_of": [], "behind": []}',
    personalization    JSONB,
    skin_binding       JSONB,
    prompt_nudge       TEXT,
    visible            BOOLEAN NOT NULL DEFAULT TRUE,
    locked             BOOLEAN NOT NULL DEFAULT FALSE,
    history            JSONB NOT NULL DEFAULT '[]',
    z_index            INTEGER NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT exactly_one_definition CHECK (
        (definition_id IS NULL) <> (inline_definition IS NULL)
    )
);
CREATE INDEX idx_asset_instances_canvas ON asset_instances(canvas_id);
CREATE INDEX idx_asset_instances_parent ON asset_instances(parent_id);
CREATE INDEX idx_asset_instances_definition ON asset_instances(definition_id);

-- The personalisation key. Storybook-series accommodations live here.
CREATE TABLE child_profiles (
    profile_id      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    pronouns        TEXT,
    likeness_refs   JSONB NOT NULL DEFAULT '[]',
    accommodations  JSONB NOT NULL DEFAULT '[]',
    age_range       TEXT,
    reading_level   TEXT,
    org_id          TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Natural container for WorldStyle + StyleVolume[].
CREATE TABLE books (
    book_id        TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    world_style    JSONB NOT NULL,
    style_volumes  JSONB NOT NULL DEFAULT '[]',
    profile_id     TEXT REFERENCES child_profiles(profile_id) ON DELETE SET NULL,
    org_id         TEXT NOT NULL DEFAULT '',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

The existing `canvases` table is unchanged; a future migration may add
a nullable `book_id` foreign key to associate a canvas with a book and
its world style. That's deferred until the compositor (ADR-041) needs
it.

### Module surface

```python
# packages/maistro-canvas/src/maistro_canvas/canvas/asset_store.py

class InMemoryAssetStore:
    """Ephemeral test store. Implements AssetRegistry + the rest."""

class PostgresAssetStore:
    """Production store. Raw SQL via sqlalchemy text(), async,
    matching the existing canvas store.py pattern."""

# Both expose:
async def register_definition(self, defn: AssetDefinition) -> AssetDefinition
async def get_definition(self, asset_id: str) -> AssetDefinition | None
async def list_definitions_by_kind(self, kind: str) -> list[AssetDefinition]
async def update_definition(self, defn: AssetDefinition) -> AssetDefinition

async def upsert_sheet(self, sheet: AssetSheet) -> AssetSheet
async def get_sheet(self, asset_id: str) -> AssetSheet | None
async def regenerate_sheet(self, asset_id: str, sheet_image: str,
                           refs: tuple[str, ...] | None = None,
                           params: dict[str, Any] | None = None) -> AssetSheet

async def upsert_instance(self, instance: AssetInstance) -> AssetInstance
async def get_instance(self, instance_id: str) -> AssetInstance | None
async def list_instances(self, canvas_id: str) -> list[AssetInstance]
async def remove_instance(self, instance_id: str) -> None

async def upsert_profile(self, profile: ChildProfile) -> ChildProfile
async def get_profile(self, profile_id: str) -> ChildProfile | None

async def create_book(self, *, book_id: str, title: str,
                      world_style: WorldStyle,
                      style_volumes: tuple[StyleVolume, ...] = (),
                      profile_id: str | None = None) -> Book
async def get_book(self, book_id: str) -> Book | None
async def update_book(self, book: Book) -> Book
```

### Boundary contracts

- `register_definition` is **idempotent** on `asset_id`: re-registering
  a definition with identical canonical fields is a no-op; with
  differing canonical fields it raises `ValueError` (ADR-039 EC-04).
- `upsert_instance` validates the embedded inline definition (if any)
  against the same Pydantic schema as a registered one.
- `regenerate_sheet` increments `revision` atomically; concurrent
  regenerations on the same `asset_id` cannot produce identical
  revision numbers (`SELECT ... FOR UPDATE` in the Postgres store).
- Inline definitions never escape an `asset_instances` row — they are
  stored verbatim in `inline_definition` JSONB and not promoted to
  `asset_definitions` automatically.
- A canvas with `org_id != ''` returns instances scoped to that org;
  unscoped (`org_id == ''`) is the standalone-Canvas-Studio default.

### Behavioral contracts

- After `register_definition(D); register_definition(D)`, the registry
  contains exactly one row for `D.asset_id`.
- `regenerate_sheet` is **monotonic**: the new revision is strictly
  greater than the previous.
- `list_instances(canvas_id)` returns instances ordered by
  `(z_index ASC, created_at ASC)` — siblings of the same parent
  preserve insertion order at equal z.
- `remove_instance` cascades `parent_id` references to NULL on
  child rows; children become orphans, not deleted (a render-time
  validation step would catch this and raise `MissingSocketError`
  per ADR-039).

## Consequences

- ADR-041 (compositor) gets a real persistence to walk: the scene
  graph is reconstructed by joining `asset_instances` with their
  parent rows.
- ADR-042 (FastAPI routes) gets concrete CRUD methods to wrap.
- The legacy `LayerRecord` model in `store.py` continues to work; the
  data-migration ADR (TBD) handles the move from `layers` to
  `asset_instances`.
- `stronghold` multi-tenancy gets a natural extension via the existing
  `org_id` column already standard on every store table.

## Out of scope

- Image rendering / compositing — ADR-041.
- HTTP routes — ADR-042.
- Agent / tool integration — ADR-043.
- Migrating existing `LayerRecord` rows to `AssetInstance` — separate
  ADR after the compositor lands.
- Tenant-scoped ontology entries (per ADR-036 Dynamic facet) — v2.0.

## Source references

- `packages/maistro-canvas/src/maistro_canvas/layers.py` — types this
  store persists.
- `packages/maistro-canvas/src/maistro_canvas/protocols.py` — protocols
  this store implements.
- `packages/maistro-canvas/src/maistro_canvas/canvas/store.py` — pattern
  for raw SQL + async + row coercion.
- `alembic/versions/001_initial_memory_schema.py` — migration shape.

## Links

- PR: (this PR)
- Follow-up ADRs: ADR-041 (compositor), ADR-042 (routes), ADR-043
  (executor + tool).
