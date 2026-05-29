# CLAUDE.md — hive-conductor

This file provides guidance to Claude Code (claude.ai/code) when working in `packages/hive-conductor/`.

The Agent Conductor app (household/personal): FastAPI backend + React SPA. Unlike the library packages, this is
an **application** — no `pyproject.toml`, deps live in `backend/requirements.txt`.

## Backend

```bash
cd packages/hive-conductor/backend
uv pip install -r requirements.txt
cp .env.example .env          # then fill in values
uvicorn main:app --reload --port 8101
```

- Entry: `main:app` on port **8101**. Routes registered in `main.py`; handlers under `routes/`.
- Config via `backend/.env`: `LITELLM_API_BASE`, `LITELLM_API_KEY`, `CHAT_DEFAULT_MODEL`, `CONDUCTOR_DATA_DIR`,
  `HARDWARE_PRESET`. No DB required by default (in-memory stores; optional SQLite via `CONDUCTOR_STATE_DB`).

### Tests

```bash
pytest packages/hive-conductor/backend/tests/
```
`backend/tests/conftest.py` adds `backend/` to `sys.path`, stubs the engine/foundation singletons, seeds test
users, and provides `authed_client` / `admin_client` fixtures (auto-login). No manual PYTHONPATH needed.

## Frontend

```bash
cd packages/hive-conductor/frontend
npm ci
npm run dev      # Vite dev server (5173), proxies /v1 and /health → backend :8101
npm run build    # tsc + vite build
npm run lint     # ESLint
```

Package manager is **npm** (package-lock.json).

## Docker

`docker compose up --build` (or build from `Dockerfile`) for the production-style run.
