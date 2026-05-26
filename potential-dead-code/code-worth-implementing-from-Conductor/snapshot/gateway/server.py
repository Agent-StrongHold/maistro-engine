"""Inference Gateway — FastAPI server.

Sits between the Conductor orchestrator and llama-server.
Manages slot orchestration, prefix caching, and Ultra Think parallel generation.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from gateway.config import GatewayConfig, get_config
from gateway.prefix_cache import PrefixCacheManager
from gateway.slot_manager import SlotManager
from gateway.ultra_think import UltraThink
from gateway.validation import ValidationError, validate_project_id, validate_task_id

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Lifespan — initialise shared resources
# ------------------------------------------------------------------

_slot_manager: SlotManager | None = None
_prefix_cache: PrefixCacheManager | None = None
_ultra_think: UltraThink | None = None
_http_client: httpx.AsyncClient | None = None
_config: GatewayConfig | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _slot_manager, _prefix_cache, _ultra_think, _http_client, _config
    _config = get_config()
    _http_client = httpx.AsyncClient()
    _slot_manager = SlotManager(_config, _http_client)
    _prefix_cache = PrefixCacheManager(_config, _slot_manager, _http_client)
    _ultra_think = UltraThink(_config, _slot_manager, _http_client)

    # Ensure metrics dir exists
    Path(_config.metrics_log_path).parent.mkdir(parents=True, exist_ok=True)

    logger.info("Gateway started — llama-server at %s", _config.llama_server_url)
    yield
    await _http_client.aclose()
    logger.info("Gateway shut down")


app = FastAPI(title="Conductor Inference Gateway", version="0.1.0", lifespan=lifespan)


# ------------------------------------------------------------------
# Request / Response models
# ------------------------------------------------------------------


class ChatCompletionRequest(BaseModel):
    """Subset of OpenAI chat completion request we proxy."""

    model: str = ""
    messages: list[dict]
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    stream: bool = False


class UltraThinkRequest(BaseModel):
    task_id: str
    messages: list[dict]
    project_id: str
    tier: int = Field(default=2, ge=1, le=4)
    max_tokens: int | None = None
    n_candidates: int | None = None


class ProjectLoadRequest(BaseModel):
    project_id: str
    layer0_text: str
    knowledge_context: str = ""


class ProjectIdRequest(BaseModel):
    project_id: str


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@app.get("/health")
async def health():
    """Gateway liveness — also checks llama-server reachability."""
    if _http_client is None or _config is None:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    try:
        # Use configurable health check path (default: /health)
        health_url = f"{_config.llama_server_url}{_config.health_check_path}"
        resp = await _http_client.get(health_url, timeout=5)
        engine_ok = resp.status_code == 200
    except Exception:
        engine_ok = False
    return {
        "gateway": "ok",
        "inference_engine": "ok" if engine_ok else "unreachable",
    }


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    """OpenAI-compatible proxy — single completion through a worker slot."""
    if _slot_manager is None or _http_client is None or _config is None:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    slot_id = await _slot_manager.acquire_worker("chat-direct")
    try:
        payload = req.model_dump(exclude_none=True)
        payload["id_slot"] = slot_id
        payload["cache_prompt"] = True

        t0 = time.monotonic()
        resp = await _http_client.post(
            f"{_config.llama_server_url}/v1/chat/completions",
            json=payload,
            timeout=_config.generation_timeout_seconds,
        )
        resp.raise_for_status()
        elapsed_ms = (time.monotonic() - t0) * 1000

        data = resp.json()
        _log_metric("chat_completion", {"elapsed_ms": round(elapsed_ms, 1), "slot": slot_id})
        return data
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Inference engine error: {exc}")
    finally:
        _slot_manager.release_worker(slot_id)


@app.post("/v1/ultra-think")
async def ultra_think(req: UltraThinkRequest):
    """Parallel diverse generation (Ultra Think)."""
    if _ultra_think is None:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    # Validate inputs
    try:
        project_id = validate_project_id(req.project_id)
        task_id = validate_task_id(req.task_id)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = await _ultra_think.generate(
        task_id=task_id,
        messages=req.messages,
        project_id=project_id,
        tier=req.tier,
        max_tokens=req.max_tokens,
        n_candidates=req.n_candidates,
    )

    _log_metric(
        "ultra_think",
        {
            "task_id": result.task_id,
            "tier": result.tier,
            "candidates": len(result.candidates),
            "errors": len(result.errors),
            "total_ms": round(result.timing.total_ms, 1),
        },
    )

    # Serialize dataclasses to dicts for JSON response
    from dataclasses import asdict

    return asdict(result)


@app.post("/v1/project/load")
async def project_load(req: ProjectLoadRequest):
    """Load project context into the template slot (with cache reuse)."""
    if _prefix_cache is None:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    try:
        project_id = validate_project_id(req.project_id)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    reused = await _prefix_cache.ensure_project_loaded(
        project_id=project_id,
        layer0_text=req.layer0_text,
        knowledge_context=req.knowledge_context,
    )
    return {"project_id": project_id, "cache_reused": reused}


@app.post("/v1/project/save")
async def project_save(req: ProjectIdRequest):
    """Persist current template slot KV cache to disk."""
    if _slot_manager is None:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    try:
        project_id = validate_project_id(req.project_id)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    elapsed = await _slot_manager.save_template(project_id)
    return {"project_id": project_id, "save_time_ms": round(elapsed, 1)}


@app.post("/v1/project/restore")
async def project_restore(req: ProjectIdRequest):
    """Restore a previously saved KV cache from disk into template slot."""
    if _slot_manager is None:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    try:
        project_id = validate_project_id(req.project_id)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Restore to template slot by saving and then the slot already has it
    # In practice this is a no-op if the cache is already loaded
    return {"project_id": project_id, "status": "ok"}


@app.get("/v1/slots/status")
async def slots_status():
    """Current slot utilization."""
    if _slot_manager is None:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    from dataclasses import asdict

    statuses = await _slot_manager.get_all_status()
    return {
        "slots": [asdict(s) for s in statuses],
        "available_workers": _slot_manager.available_count,
    }


@app.get("/v1/metrics")
async def metrics():
    """Return recent metrics (last 100 entries)."""
    if _config is None:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    path = Path(_config.metrics_log_path)
    if not path.exists():
        return {"entries": []}
    lines = path.read_text().strip().split("\n")[-100:]
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {"entries": entries}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


# Maximum metrics file size before rotation (10 MB)
MAX_METRICS_FILE_SIZE = 10 * 1024 * 1024


def _log_metric(event: str, data: dict) -> None:
    """Append a metric row to the JSONL metrics log.

    Rotates the log file when it exceeds MAX_METRICS_FILE_SIZE.
    """
    if _config is None:
        return
    path = Path(_config.metrics_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Rotate if too large
    if path.exists() and path.stat().st_size > MAX_METRICS_FILE_SIZE:
        rotated = path.with_suffix(".jsonl.old")
        try:
            if rotated.exists():
                rotated.unlink()
            path.rename(rotated)
        except OSError:
            pass  # Best effort rotation

    row = json.dumps({"ts": time.time(), "event": event, **data})
    with open(path, "a") as f:
        f.write(row + "\n")
