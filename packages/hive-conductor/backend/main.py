"""Hive Conductor FastAPI entrypoint: API + optional static SPA."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from config import get_settings
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from logging_setup import configure_logging
from middleware.auth import AuthMiddleware
from middleware.request_log import RequestLogMiddleware
from pydantic import BaseModel, ConfigDict
from routes import (
    agents,
    audit,
    auth,
    capabilities,
    chat,
    cli,
    containers,
    credentials,
    dag_runs,
    dags,
    dashboard_layout,
    design,
    eval_judge,
    feedback,
    harness,
    health,
    install,
    mcp,
    memory,
    messages,
    missions,
    program,
    quotas,
    schedules,
    setup,
    setup_checklist,
    skills,
    topology,
    voice,
    widgets,
    work_items,
    ws,
)
from routes import (
    metrics as metrics_r,
)
from routes import (
    optimizer as optimizer_r,
)
from routes import settings as settings_r
from services import engine as engine_service
from services import foundation as foundation_service
from services.ha_tools import get_all_confirms, get_pending_confirms, respond_confirm

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "frontend" / "dist"


class ConfirmResponseBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    response: str


_confirms_router = APIRouter(tags=["confirms"])


@_confirms_router.get("")
def list_confirms():
    return get_all_confirms()


@_confirms_router.get("/pending")
def list_pending():
    return get_pending_confirms()


@_confirms_router.post("/{confirm_id}/respond")
async def respond_to_confirm(confirm_id: str, body: ConfirmResponseBody):
    return await respond_confirm(confirm_id, body.response)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    import logging as _logging

    import stores
    from settings_defaults import apply_default_settings_if_needed

    _lifespan_log = _logging.getLogger("hive.lifespan")
    try:
        await foundation_service.start_foundation(get_settings())
    except Exception as exc:
        _lifespan_log.warning("foundation_start_failed: %s", exc, exc_info=True)
        stores.initialize_stores()
    apply_default_settings_if_needed()
    try:
        await engine_service.start_engine(get_settings())
    except Exception as exc:
        _lifespan_log.warning("engine_start_failed: %s", exc, exc_info=True)
    try:
        from services.design_service import start_design_service

        await start_design_service(get_settings())
        from services.design_preview import init_design_preview_service
        from services.design_render import init_design_render_service

        init_design_preview_service()
        init_design_render_service()
        _lifespan_log.info("Design preview and render services initialized")
    except Exception as exc:
        _lifespan_log.warning("design_service_start_failed: %s", exc, exc_info=True)
    try:
        # Day 8 — wire pm_runner's event bus into the DAG-run store so
        # /v1/dag-runs/{id}/events SSE streams pick up live pm_node_*
        # events from PM-fleet invocations. No-op if pm_runner isn't
        # importable (e.g. when MAISTRO_POC_MODE != "pm").
        from services.dag_run_store import install_pm_event_bridge

        install_pm_event_bridge()
    except Exception:
        _lifespan_log.warning("pm_event_bridge_install_failed", exc_info=True)
    try:
        from services.scheduler import start_scheduler

        start_scheduler()
    except Exception as exc:
        _lifespan_log.warning("scheduler_start_failed: %s", exc, exc_info=True)
    try:
        from services.evolution import start_evolution

        await start_evolution()
    except Exception as exc:
        _lifespan_log.warning("evolution_start_failed: %s", exc, exc_info=True)
    yield
    try:
        from services.design_service import stop_design_service

        await stop_design_service()
    except Exception as exc:
        _lifespan_log.warning("design_service_stop_failed: %s", exc)
    try:
        from services.evolution import stop_evolution

        await stop_evolution()
    except Exception as exc:
        _lifespan_log.warning("evolution_stop_failed: %s", exc)
    try:
        from services.scheduler import stop_scheduler

        stop_scheduler()
    except Exception as exc:
        _lifespan_log.warning("scheduler_stop_failed: %s", exc)
    await engine_service.stop_engine()
    await foundation_service.stop_foundation()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Hive Conductor", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(AuthMiddleware)

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/v1/auth")
    app.include_router(credentials.router, prefix="/v1/credentials")
    app.include_router(install.router, prefix="/v1/install")
    app.include_router(chat.router, prefix="/v1/chat")
    app.include_router(missions.router, prefix="/v1/tasks")
    app.include_router(schedules.router, prefix="/v1/schedules")
    app.include_router(skills.router, prefix="/v1/skills")
    app.include_router(agents.router, prefix="/v1/agents")
    app.include_router(program.router, prefix="/v1/program")
    app.include_router(work_items.router, prefix="/v1/work-items")
    app.include_router(mcp.router, prefix="/v1/mcp")
    app.include_router(cli.router, prefix="/v1/cli")
    app.include_router(containers.router, prefix="/v1/containers")
    app.include_router(memory.router, prefix="/v1/memory")
    app.include_router(settings_r.router, prefix="/v1/settings")
    app.include_router(capabilities.router, prefix="/v1/capabilities")
    app.include_router(harness.router, prefix="/v1/harness")
    app.include_router(voice.router, prefix="/v1/voice")
    app.include_router(ws.router, prefix="/v1/ws")
    app.include_router(setup.router, prefix="/v1/setup")
    app.include_router(setup_checklist.router, prefix="/v1/setup-checklist")
    app.include_router(widgets.router, prefix="/v1/widgets")
    from routes import daily_report_v2

    app.include_router(daily_report_v2.router, prefix="/v1/daily-report")
    app.include_router(dags.router, prefix="/v1/dags")
    app.include_router(dashboard_layout.router)
    app.include_router(widgets.router, prefix="/v1/widgets")
    app.include_router(dag_runs.router, prefix="/v1/dag-runs")
    # Phase 5 Signal #4: thumbs feedback piggybacks on /v1/dag-runs path
    # space so the SSE stream + feedback live together for the client.
    app.include_router(feedback.router, prefix="/v1/dag-runs")
    # Phase 5 Signal #5 — per-node latency + token aggregates. NOTE: a
    # separate prefix is needed because /v1/dag-runs/{run_id} would
    # otherwise greedily match /v1/dag-runs/metrics as run_id="metrics".
    app.include_router(metrics_r.router, prefix="/v1/dag-metrics")
    # Phase 5 Signal #3: eval-judge is an INTERNAL maistro agent
    # (LiteLLM-backed, NOT a Claude Code subagent). Endpoints expose the
    # verdict store + a manual trigger.
    app.include_router(eval_judge.router, prefix="/v1/eval-judge")
    # Phase 6 — optimizer endpoints (auto-apply gated by edit_lock; propose
    # surfaces for user accept/reject).
    app.include_router(optimizer_r.router, prefix="/v1/optimizer")
    # Phase 7 — topology variant comparison.
    app.include_router(topology.router, prefix="/v1/topology")
    app.include_router(messages.router, prefix="/v1/messages")
    app.include_router(audit.router, prefix="/v1/audit")
    app.include_router(quotas.router, prefix="/v1/quotas")
    app.include_router(_confirms_router, prefix="/v1/confirms")
    app.include_router(design.router, prefix="/v1")

    # Phase 6 — Canvas/Davinci DAG
    try:
        from routes.canvas import router as canvas_router

        app.include_router(canvas_router)
    except Exception:
        pass

    # Phase 7 — PM Fleet v2 (distillation, GitHub/GitLab tools, topK)
    try:
        from routes.pm_fleet_v2 import router as pm_fleet_v2_router

        app.include_router(pm_fleet_v2_router)
    except Exception:
        pass

    try:
        from routes.evolution import router as evolution_router

        app.include_router(evolution_router, prefix="/v1/evolution")
    except Exception as exc:
        import logging as _logging

        _logging.getLogger("hive.lifespan").warning(
            "evolution_router_unavailable: %s",
            exc,
        )

    if STATIC_DIR.is_dir():
        from starlette.responses import FileResponse

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            # Do not return the SPA shell for unknown API paths (avoids JSON parse errors in the UI).
            if full_path.startswith("v1/"):
                from starlette.responses import JSONResponse

                return JSONResponse(status_code=404, content={"detail": "Not Found"})
            fp = STATIC_DIR / full_path
            if fp.is_file():
                return FileResponse(fp)
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
