---
id: SPEC-176
title: Hive Conductor monorepo package
repo: maistro-engine
kind: spec
status: Implemented
created: 2026-05-13
accepted: 2026-05-13
implemented: 2026-05-13
substrate:
  - maistro-engine#ADR-002
implements: []
related:
  - maistro-engine#SPEC-175
  - maistro-engine#SPEC-177
source:
  - packages/hive-conductor/
contracts:
  - boundary
tests:
  - packages/hive-conductor/backend/tests/test_api.py
layer: Orchestration
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-176: Hive Conductor monorepo package

## Context

Hive Conductor is a **mission-control style UI** with a **FastAPI stub** for local demos and wiring tests. It lives under **`packages/hive-conductor/`** in `maistro-engine` (not as a separate product repo for v1).

## Decision

- **Layout:** `frontend/` (Vite + React 19 + TypeScript), `backend/` (FastAPI + in-memory stores), `Dockerfile`, `docker-compose.yml`, and package `README.md`.
- **Ports:** API and production SPA are served on **8101**. **maistro-server** remains on ~**8000**; phase 1 does **not** mount Hive into maistro-server.
- **Naming:** Hive **`GET /v1/tasks`** exposes **missions** (orchestration units). **Maistro core `GET /tasks`** is a different domain. Callers must not conflate the two until an explicit integration layer exists.
- **Dev wiring:** Vite dev server proxies **`/v1`** and **`/health`** to `127.0.0.1:8101`. The UI uses **relative** `fetch` paths.
- **Prod wiring:** Multi-stage Docker image builds the SPA into `frontend/dist`; FastAPI serves **`StaticFiles`** with `html=True` for SPA deep links when the dist directory is present.
- **Databases:** If LiteLLM (or similar) is run alongside this stub, use a **separate** `DATABASE_URL` for LiteLLM’s store vs any future Hive persistence.
- **Phase 2 (non-goals for this spec):** Delegation to `maistro-server` / `maistro-core` for real task execution, auth, and persistence.

## Out of scope (explicit)

- **JedAI**, **dev-ai-environment**, and **force-convergence** prototypes are **not** imported or required by this package. If they must integrate later, add paths and reuse notes per `docs/install/resolver-matrix.md` and extend acceptance criteria in a follow-on spec.

## Acceptance criteria

1. `uvicorn main:app --port 8101` from `packages/hive-conductor/backend` exposes `/health`, `/health/ready`, and `/v1/*` routes used by the UI.
2. `npm run dev` in `packages/hive-conductor/frontend` proxies API calls to 8101.
3. `docker build -f packages/hive-conductor/Dockerfile packages/hive-conductor` produces an image that serves API + SPA on 8101.
4. CI runs **frontend build** and **backend pytest** for this package (see `.github/workflows/ci.yml`).

## References

- [packages/hive-conductor/README.md](../../packages/hive-conductor/README.md)
- [docs/install/resolver-matrix.md](../install/resolver-matrix.md) (external prototypes note)
