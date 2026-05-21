"""Slot Manager — manages llama-server KV cache slots.

Slot 0 is the template slot: holds pre-warmed project context.
Slots 1-N are worker slots used for actual generation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

from gateway.config import GatewayConfig

logger = logging.getLogger(__name__)


@dataclass
class SlotStatus:
    slot_id: int
    state: str  # "idle", "processing", "reserved"
    task_id: str | None = None
    cached_prefix_tokens: int = 0


@dataclass
class SlotMetrics:
    slot_restore_time_ms: float = 0.0
    prefix_tokens_cached: int = 0
    suffix_tokens_processed: int = 0
    generation_time_ms: float = 0.0
    tokens_per_second: float = 0.0


class SlotManager:
    """Manages llama-server slots for the Conductor system.

    Slot allocation strategy:
    - Slot 0: Template slot. NEVER used for generation directly.
    - Slots 1-4: Worker slots for actual generation.
    """

    def __init__(self, config: GatewayConfig, client: httpx.AsyncClient) -> None:
        self._config = config
        self._client = client
        self._base_url = config.llama_server_url
        self._template_slot = config.template_slot_id
        self._worker_slots = list(config.worker_slot_ids)
        # Track which worker slots are currently available
        self._available: asyncio.Queue[int] = asyncio.Queue()
        for sid in self._worker_slots:
            self._available.put_nowait(sid)
        self._slot_states: dict[int, SlotStatus] = {
            sid: SlotStatus(slot_id=sid, state="idle") for sid in self._worker_slots
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def acquire_worker(self, task_id: str, timeout: float | None = None) -> int:
        """Acquire a free worker slot. Blocks until one is available."""
        timeout = timeout or self._config.generation_timeout_seconds
        try:
            slot_id = await asyncio.wait_for(self._available.get(), timeout=timeout)
        except asyncio.TimeoutError:
            raise RuntimeError(f"No worker slot available within {timeout}s for task {task_id}")
        self._slot_states[slot_id] = SlotStatus(
            slot_id=slot_id, state="reserved", task_id=task_id
        )
        logger.info("Acquired slot %d for task %s", slot_id, task_id)
        return slot_id

    def release_worker(self, slot_id: int) -> None:
        """Return a worker slot to the pool."""
        if slot_id == self._template_slot:
            raise ValueError("Cannot release the template slot as a worker")
        self._slot_states[slot_id] = SlotStatus(slot_id=slot_id, state="idle")
        self._available.put_nowait(slot_id)
        logger.info("Released slot %d", slot_id)

    async def save_template(self, project_id: str) -> float:
        """Save the template slot's KV cache to disk. Returns time in ms."""
        return await self._slot_action(
            self._template_slot, "save", f"template-{project_id}"
        )

    async def restore_template_to_worker(self, project_id: str, worker_slot_id: int) -> float:
        """Restore the saved template cache into a worker slot. Returns time in ms."""
        if worker_slot_id == self._template_slot:
            raise ValueError("Cannot restore into the template slot")
        return await self._slot_action(
            worker_slot_id, "restore", f"template-{project_id}"
        )

    async def get_all_status(self) -> list[SlotStatus]:
        """Return status of all managed slots."""
        return list(self._slot_states.values())

    @property
    def available_count(self) -> int:
        return self._available.qsize()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _slot_action(self, slot_id: int, action: str, filename: str) -> float:
        """Send a save/restore action to the llama-server /slots API."""
        url = f"{self._base_url}/slots/{slot_id}?action={action}"
        payload = {"filename": filename}
        t0 = time.monotonic()
        try:
            resp = await self._client.post(
                url, json=payload, timeout=self._config.slot_restore_timeout_seconds
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Slot %s on slot %d failed: %s", action, slot_id, exc)
            raise
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info("Slot %s(%s) on slot %d took %.1fms", action, filename, slot_id, elapsed_ms)
        return elapsed_ms
