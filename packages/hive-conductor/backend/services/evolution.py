"""Evolution service — wires maistro-evolve into hive-conductor.

Runs background evolution cycles, exposes the population via API,
and provides the hyperagent self-improvement loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_service: _EvolutionService | None = None


def get_evolution_service() -> _EvolutionService:
    if _service is None:
        raise RuntimeError("EvolutionService not started")
    return _service


async def start_evolution() -> None:
    global _service
    _service = _EvolutionService()
    asyncio.ensure_future(_service.run_loop())


async def stop_evolution() -> None:
    global _service
    if _service is not None:
        _service.stop()
        _service = None


class _EvolutionService:
    def __init__(self) -> None:
        self._running = True
        self._population: Any = None
        self._cycle_count = 0
        self._last_cycle_error: str | None = None

    def stop(self) -> None:
        self._running = False

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    @property
    def population(self) -> Any:
        return self._population

    async def run_loop(self) -> None:
        try:
            from maistro_evolve.population import PopulationStore
            self._population = PopulationStore()
        except Exception as exc:
            logger.warning("Evolution population init failed: %s", exc)
            return

        while self._running:
            await asyncio.sleep(300)
            if not self._running:
                break
            try:
                await self._run_one_cycle()
            except Exception as exc:
                self._last_cycle_error = str(exc)
                logger.warning("Evolution cycle failed: %s", exc)

    async def _run_one_cycle(self) -> None:
        from maistro_evolve.cycle import EvolutionCycle, EvolutionConfig
        from maistro_evolve.harness import EvalHarness

        config = EvolutionConfig()
        harness = EvalHarness(use_real_benchmarks=True)

        cycle = EvolutionCycle(harness=harness)
        await cycle.run_cycle(
            population=self._population,
            llm_call=self._build_llm_call(),
            config=config,
        )
        self._cycle_count += 1
        logger.info("Evolution cycle %d complete, population: %d", self._cycle_count, len(self._population._genomes))

    def _build_llm_call(self):
        try:
            from config import get_settings
            import httpx

            settings = get_settings()
            base = settings.maistro_llm_base_url or settings.litellm_api_base
            key = settings.maistro_llm_api_key or settings.litellm_api_key
            if not base:
                return None
            raw_key = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key) if key else ""

            async def _llm_call(messages: list[dict], **kwargs: Any) -> str:
                import json
                headers = {"Content-Type": "application/json"}
                if raw_key:
                    headers["Authorization"] = f"Bearer {raw_key}"
                payload = {
                    "model": kwargs.get("model", settings.chat_default_model),
                    "messages": messages,
                    "temperature": kwargs.get("temperature", 0.3),
                    "max_tokens": kwargs.get("max_tokens", 4096),
                }
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(f"{base}/v1/chat/completions", json=payload, headers=headers)
                    resp.raise_for_status()
                    return resp.json()["choices"][0]["message"]["content"]
            return _llm_call
        except Exception:
            return None

    def status(self) -> dict:
        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "population_size": len(self._population._genomes) if self._population else 0,
            "last_error": self._last_cycle_error,
        }
