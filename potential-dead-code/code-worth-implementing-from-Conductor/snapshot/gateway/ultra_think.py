"""Ultra Think — parallel diverse generation orchestrator.

Generates N candidate completions for the same task with varied sampling
parameters, then returns all candidates for the Conductor to evaluate.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field

import httpx

from gateway.config import GatewayConfig
from gateway.slot_manager import SlotManager

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Sampling diversity profiles
# ------------------------------------------------------------------

DIVERSITY_PROFILES: list[dict] = [
    {"temperature": 0.7, "top_p": 0.9, "top_k": 30, "label": "conservative"},
    {"temperature": 1.0, "top_p": 0.95, "top_k": 40, "label": "standard"},
    {"temperature": 1.2, "top_p": 0.98, "top_k": 50, "label": "exploratory"},
    {"temperature": 1.0, "top_p": 0.95, "top_k": 40, "presence_penalty": 0.3, "label": "creative"},
    {"temperature": 0.8, "top_p": 0.85, "top_k": 20, "label": "focused"},
]

SYSTEM_PROMPT_SUFFIXES: list[str] = [
    "Prioritize readability and maintainability.",
    "Optimize for performance and efficiency.",
    "Focus on robustness and error handling.",
    "Emphasize simplicity and minimal code.",
    "Consider edge cases and defensive programming.",
]


# ------------------------------------------------------------------
# Result types
# ------------------------------------------------------------------


@dataclass
class CandidateCompletion:
    candidate_id: str
    slot_id: int
    content: str
    sampling_params: dict
    system_prompt_variant: str
    tokens_generated: int
    generation_time_ms: float
    tokens_per_second: float


@dataclass
class UltraThinkTiming:
    slot_restore_ms: float
    parallel_generation_ms: float
    total_ms: float
    prefix_tokens_cached: int
    suffix_tokens_per_candidate: list[int]


@dataclass
class UltraThinkResult:
    task_id: str
    tier: int
    candidates: list[CandidateCompletion]
    timing: UltraThinkTiming
    errors: list[str] = field(default_factory=list)


# ------------------------------------------------------------------
# Orchestrator
# ------------------------------------------------------------------


class UltraThink:
    """Generate N diverse completions for the same prompt in parallel."""

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

    async def generate(
        self,
        task_id: str,
        messages: list[dict],
        project_id: str,
        tier: int = 2,
        max_tokens: int | None = None,
        n_candidates: int | None = None,
    ) -> UltraThinkResult:
        """Run an Ultra Think cycle at the given tier."""
        max_tokens = max_tokens or self._config.default_max_tokens
        if n_candidates is None:
            n_candidates = {
                1: self._config.tier1_candidates,
                2: self._config.tier2_candidates,
                3: self._config.tier3_candidates,
            }.get(tier, self._config.tier3_candidates)

        t_total_start = time.monotonic()
        slots: list[int] = []
        candidates: list[CandidateCompletion] = []
        errors: list[str] = []
        suffix_tokens: list[int] = []
        slot_restore_ms = 0.0
        parallel_gen_ms = 0.0

        try:
            # 1) Acquire worker slots
            for i in range(n_candidates):
                sid = await self._slots.acquire_worker(f"{task_id}-c{i}")
                slots.append(sid)

            # 2) Restore template cache into each worker
            t_restore_start = time.monotonic()
            restore_tasks = [
                self._slots.restore_template_to_worker(project_id, sid) for sid in slots
            ]
            restore_results = await asyncio.gather(*restore_tasks, return_exceptions=True)
            slot_restore_ms = (time.monotonic() - t_restore_start) * 1000

            # Log any restore errors (non-fatal, generation may still work)
            for i, restore_result in enumerate(restore_results):
                if isinstance(restore_result, BaseException):
                    logger.warning("Slot restore failed for slot %d: %s", slots[i], restore_result)

            # 3) Fire parallel generations
            t_gen_start = time.monotonic()
            gen_tasks = []
            for i, sid in enumerate(slots):
                profile = DIVERSITY_PROFILES[i % len(DIVERSITY_PROFILES)]
                suffix = SYSTEM_PROMPT_SUFFIXES[i % len(SYSTEM_PROMPT_SUFFIXES)]
                gen_tasks.append(
                    self._generate_one(
                        task_id=task_id,
                        candidate_index=i,
                        messages=messages,
                        slot_id=sid,
                        profile=profile,
                        system_suffix=suffix,
                        max_tokens=max_tokens,
                    )
                )
            gen_results: list[CandidateCompletion | BaseException] = await asyncio.gather(
                *gen_tasks, return_exceptions=True
            )
            parallel_gen_ms = (time.monotonic() - t_gen_start) * 1000

            # 4) Collect results
            for i, gen_result in enumerate(gen_results):
                if isinstance(gen_result, BaseException):
                    errors.append(f"candidate {i} on slot {slots[i]}: {gen_result}")
                    logger.error("Generation failed for candidate %d: %s", i, gen_result)
                else:
                    # gen_result is CandidateCompletion
                    candidates.append(gen_result)
                    suffix_tokens.append(gen_result.tokens_generated)

        finally:
            # Always release slots, even on exception
            for sid in slots:
                try:
                    self._slots.release_worker(sid)
                except Exception as e:
                    logger.error("Failed to release slot %d: %s", sid, e)

        total_ms = (time.monotonic() - t_total_start) * 1000

        timing = UltraThinkTiming(
            slot_restore_ms=slot_restore_ms,
            parallel_generation_ms=parallel_gen_ms,
            total_ms=total_ms,
            prefix_tokens_cached=0,  # filled from response usage if available
            suffix_tokens_per_candidate=suffix_tokens,
        )

        logger.info(
            "Ultra Think tier=%d produced %d/%d candidates in %.0fms",
            tier,
            len(candidates),
            n_candidates,
            total_ms,
        )

        return UltraThinkResult(
            task_id=task_id,
            tier=tier,
            candidates=candidates,
            timing=timing,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Single generation
    # ------------------------------------------------------------------

    async def _generate_one(
        self,
        task_id: str,
        candidate_index: int,
        messages: list[dict],
        slot_id: int,
        profile: dict,
        system_suffix: str,
        max_tokens: int,
    ) -> CandidateCompletion:
        """Send a single completion request to a specific slot."""
        # Append diversity suffix to the last system message or add one
        augmented = list(messages)
        if augmented and augmented[0].get("role") == "system":
            augmented[0] = {
                **augmented[0],
                "content": augmented[0]["content"] + "\n\n" + system_suffix,
            }
        else:
            augmented.insert(0, {"role": "system", "content": system_suffix})

        sampling = {k: v for k, v in profile.items() if k != "label"}
        payload = {
            "messages": augmented,
            "max_tokens": max_tokens,
            "id_slot": slot_id,
            "cache_prompt": True,
            **sampling,
        }

        t0 = time.monotonic()
        resp = await self._client.post(
            f"{self._base_url}/v1/chat/completions",
            json=payload,
            timeout=self._config.generation_timeout_seconds,
        )
        resp.raise_for_status()
        elapsed_ms = (time.monotonic() - t0) * 1000

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        tokens_gen = usage.get("completion_tokens", 0)
        tps = (tokens_gen / (elapsed_ms / 1000)) if elapsed_ms > 0 and tokens_gen > 0 else 0.0

        return CandidateCompletion(
            candidate_id=f"{task_id}-c{candidate_index}-{uuid.uuid4().hex[:8]}",
            slot_id=slot_id,
            content=content,
            sampling_params=sampling,
            system_prompt_variant=system_suffix,
            tokens_generated=tokens_gen,
            generation_time_ms=elapsed_ms,
            tokens_per_second=round(tps, 1),
        )
