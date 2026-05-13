"""Prefix Cache Manager — manages per-project KV cache lifecycle on disk.

Cache invalidation is content-hash based: if the Layer 0 text + knowledge
context changes, the cache is recomputed; otherwise it's restored from disk.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from gateway.config import GatewayConfig
from gateway.slot_manager import SlotManager

logger = logging.getLogger(__name__)


@dataclass
class CacheMeta:
    """Metadata stored alongside a KV cache file."""

    project_id: str
    content_hash: str
    token_count: int
    created_at: float  # epoch seconds


class PrefixCacheManager:
    """Manages persistent KV cache files on disk for instant project context loading.

    Directory layout (under kv_cache_dir):
        projects/{project_id}/
            template.meta.json
        metrics/
            cache_stats.jsonl
    The actual .bin cache files are written by llama-server into kv_cache_dir
    directly (controlled by --slot-save-path).
    """

    def __init__(
        self,
        config: GatewayConfig,
        slot_manager: SlotManager,
        client: httpx.AsyncClient,
    ) -> None:
        self._config = config
        self._slots = slot_manager
        self._client = client
        self._base_url = config.llama_server_url
        self._cache_root = Path(config.kv_cache_dir)
        self._cache_root.mkdir(parents=True, exist_ok=True)
        (self._cache_root / "metrics").mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def ensure_project_loaded(
        self,
        project_id: str,
        layer0_text: str,
        knowledge_context: str = "",
    ) -> bool:
        """Load project context into the template slot, reusing cache if valid.

        Returns True if cache was reused, False if recomputed.
        """
        content = layer0_text + knowledge_context
        content_hash = self._hash(content)
        meta = self._read_meta(project_id)

        if meta and meta.content_hash == content_hash:
            logger.info("Cache hit for project %s (hash %s)", project_id, content_hash[:12])
            self._log_stat(project_id, "hit", 0)
            return True

        # Cache miss — recompute by sending prefix to template slot
        logger.info("Cache miss for project %s — recomputing", project_id)
        t0 = time.monotonic()
        token_count = await self._warm_template_slot(content)
        await self._slots.save_template(project_id)
        elapsed_ms = (time.monotonic() - t0) * 1000

        self._write_meta(
            project_id,
            CacheMeta(
                project_id=project_id,
                content_hash=content_hash,
                token_count=token_count,
                created_at=time.time(),
            ),
        )
        self._log_stat(project_id, "miss", elapsed_ms)
        logger.info(
            "Cached %d tokens for project %s in %.1fms",
            token_count,
            project_id,
            elapsed_ms,
        )
        return False

    def invalidate(self, project_id: str) -> None:
        """Delete cached metadata so next load forces recomputation."""
        meta_path = self._meta_path(project_id)
        if meta_path.exists():
            meta_path.unlink()
            logger.info("Invalidated cache for project %s", project_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _warm_template_slot(self, content: str) -> int:
        """Send the prefix content to the template slot for KV computation.

        We do this by sending a completion request with cache_prompt=true
        and max_tokens=0 (if supported) or 1 to the template slot, which
        forces the server to process and cache the full prefix without
        generating any completion tokens.

        Note: Some model servers don't support max_tokens=0. If you get
        errors, set CONDUCTOR_PREFIX_WARM_MAX_TOKENS=1 in your environment.
        """
        url = f"{self._base_url}/v1/chat/completions"
        # Use max_tokens=0 to avoid generating any output (just process prefix)
        # Fallback to 1 if the server doesn't support 0
        payload = {
            "messages": [{"role": "system", "content": content}],
            "max_tokens": 0,  # Just cache, don't generate
            "cache_prompt": True,
            "id_slot": self._config.template_slot_id,
        }
        timeout = self._config.prefix_warm_timeout_seconds
        try:
            resp = await self._client.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
        except Exception as e:
            # If max_tokens=0 fails, retry with max_tokens=1
            logger.warning("max_tokens=0 failed, retrying with max_tokens=1: %s", e)
            payload["max_tokens"] = 1
            resp = await self._client.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()

        data = resp.json()
        usage = data.get("usage", {})
        return usage.get("prompt_tokens", 0)

    def _meta_path(self, project_id: str) -> Path:
        d = self._cache_root / "projects" / project_id
        d.mkdir(parents=True, exist_ok=True)
        return d / "template.meta.json"

    def _read_meta(self, project_id: str) -> CacheMeta | None:
        p = self._meta_path(project_id)
        if not p.exists():
            return None
        try:
            raw = json.loads(p.read_text())
            return CacheMeta(**raw)
        except Exception:
            logger.warning("Corrupt cache meta for %s, will recompute", project_id)
            return None

    def _write_meta(self, project_id: str, meta: CacheMeta) -> None:
        from dataclasses import asdict

        p = self._meta_path(project_id)
        p.write_text(json.dumps(asdict(meta), indent=2))

    def _log_stat(self, project_id: str, event: str, elapsed_ms: float) -> None:
        stats_path = self._cache_root / "metrics" / "cache_stats.jsonl"
        row = json.dumps(
            {
                "ts": time.time(),
                "project_id": project_id,
                "event": event,
                "elapsed_ms": round(elapsed_ms, 1),
            }
        )
        with open(stats_path, "a") as f:
            f.write(row + "\n")

    @staticmethod
    def _hash(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()
