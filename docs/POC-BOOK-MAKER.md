# Book Maker POC — Engine Specification

**Branch:** `claude/book-maker-poc-Zbbha`  
**POC Repo:** `canvas-studio-poc` (Main Character Crew brand)  
**Engine location in POC:** `canvas-studio-poc/server/engine/`

---

## What this is

The `canvas-studio-poc` repo embeds a **trimmed, self-contained** copy of the
`maistro-canvas` engine at `server/engine/`. This document records:

1. What was kept vs. stripped
2. All SPEC.md divergences from the `main` branch of this repo
3. ADR cross-references
4. How the two codebases stay in sync

---

## Architecture

```
maistro-engine (this repo)
  └── packages/maistro-canvas/  ← canonical typed layer model

canvas-studio-poc
  └── server/engine/            ← trimmed in-repo copy, POC-adapted
      ├── types.py              ← EngineError base (not AgentError)
      ├── layers.py             ← ADR-039 layer model
      ├── image_provider.py     ← SPEC-compliant Azure+Gemini provider
      └── compositor.py         ← PIL compositeScene
```

The POC image generation is **client-side** (browser → Azure directly).
The `server/engine/image_provider.py` serves the print-on-demand pipeline
and any server-initiated generation (training data, export compositing).

---

## What was stripped

| Removed | Why |
|---------|-----|
| `maistro-core` dep (`AgentError`) | POC has no maistro-core installed |
| SQLAlchemy / asyncpg | POC uses psycopg3 raw queries |
| `asset_routes.py`, `asset_store.py` | Enterprise asset registry, not needed |
| `asset_compositor.py`, `asset_executor.py` | Replaced by simplified PIL compositor |
| `tool.py` (903-line canvas tool) | Not needed for wizard POC |
| B2B auth (`auth.py`) | POC has no service keys |
| `org_id` on all records | No multi-tenancy in POC |
| Cloudflare image provider | Not in SPEC |

## What was kept

- `types.py` enums and error hierarchy (base class swapped)
- `layers.py` full ADR-039 typed layer model
- PIL compositor logic (simplified, data-URL-only)
- Image provider with Azure deployment chain

---

## SPEC.md Divergences

### 1. Azure deployment chain

**SPEC requires:**
```python
AZURE_DEPLOYMENTS = [
    ("gpt-image-1-5", "2025-04-01-preview"),   # primary
    ("gpt-image-2-1", "2025-03-01-preview"),   # fallback
]
```
`main` branch uses a single configurable `AZURE_OPENAI_ENDPOINT` env var
that already contains the deployment name. The POC splits this into a
base endpoint + deployment chain.

### 2. `input_fidelity` — always a string

**SPEC invariant `input_fidelity_string_only`:**  
Azure only accepts `'high'` or `'low'`. The float `>= 0.7 → 'high'`,
`< 0.7 → 'low'` mapping lives in `_fidelity_string()`.

`main` branch had no `azureImageEdit` at all (image editing was not
implemented in the Python side).

### 3. `BookLayer` with history[] invariant

POC adds `BookLayer` dataclass to `types.py` (not present on `main`):

```python
@dataclass
class BookLayer:
    name: str
    layer_type: str
    image_url: str | None
    history: list[str]   # old images, push before replace
    quality: str         # 'draft' | 'final'
    ...

    def retry(self, new_url: str) -> BookLayer: ...
    def upgrade(self, new_url: str) -> BookLayer: ...
```

**Invariant `version_history_never_loses_images`:** `retry()` and
`upgrade()` always push the old `image_url` to `history[]` before
replacing it.

### 4. `ChildProfile.likeness_refs` capped at 5

**SPEC invariant `photo_count_capped_at_5`:**  
`ChildProfile.__post_init__` silently truncates `likeness_refs` to 5
entries. On `main` there is no cap.

### 5. 180-second timeout

**SPEC:** All generation calls have a 180s timeout with `AbortController`
(client-side) or `httpx.AsyncClient(timeout=180.0)` (server-side).
`main` branch used provider-specific timeouts (60s / 180s / 120s).

### 6. `generateImage` never returns `None`

**SPEC invariant `generation_never_returns_null`:**  
`generate_image()` catches all exceptions and returns a gradient
placeholder data URL as the last resort. Never `None`, never raises.

### 7. multipart/form-data for edits

**SPEC invariant `multipart_for_edits`:**  
`azure_image_edit()` always sends `multipart/form-data` with `image[]`
fields (one per reference image). Never `application/json`.

---

## ADR Cross-references

| ADR | Topic | Status in POC |
|-----|-------|---------------|
| ADR-039 | Typed layer model (LayerKind, Slot, Anchor, etc.) | Implemented in `server/engine/layers.py` |
| ADR-040 | Compositor (PIL-based RGBA layer assembly) | Simplified implementation in `server/engine/compositor.py` |
| ADR-041 | Image provider (Azure deployment chain) | `server/engine/image_provider.py` |
| ADR-042 | Personalisation (ChildProfile, likeness_refs) | `server/engine/layers.py::ChildProfile` |
| ADR-043 | World style + style volumes | `server/engine/layers.py::WorldStyle` |

---

## Sync strategy

The POC copy in `canvas-studio-poc/server/engine/` is intentionally a
**fork, not a submodule**. When the POC spec stabilises:

1. `BookLayer` and `ChildProfile` photo-cap will be back-ported to
   `packages/maistro-canvas/src/maistro_canvas/types.py` and
   `packages/maistro-canvas/src/maistro_canvas/layers.py` on `main`.
2. The engine deployment-chain and `azureImageEdit` will be added to
   `packages/maistro-canvas/src/maistro_canvas/canvas/asset_executor.py`.
3. `canvas-studio-poc` will then add `maistro-canvas` as a proper
   package dependency and delete `server/engine/`, completing the
   ADR-003 migration path.
