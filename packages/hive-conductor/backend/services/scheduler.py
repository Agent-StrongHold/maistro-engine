"""Background schedule runner — evaluates cron expressions and fires scheduled missions.

Uses a lightweight cron matcher (no external deps) for common patterns.
Runs as an asyncio background task started by the app lifespan.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

_runner: _ScheduleRunner | None = None


def start_scheduler() -> None:
    global _runner
    if _runner is not None:
        return
    _runner = _ScheduleRunner()
    asyncio.ensure_future(_runner.run())


def stop_scheduler() -> None:
    global _runner
    if _runner is not None:
        _runner.stop()
        _runner = None


class _ScheduleRunner:
    def __init__(self) -> None:
        self._running = True
        self._last_check: datetime | None = None

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        self._last_check = datetime.now(UTC)
        while self._running:
            await asyncio.sleep(30)
            try:
                await self._tick()
            except Exception as exc:
                logger.warning("Schedule tick failed: %s", exc)

    async def _tick(self) -> None:
        now = datetime.now(UTC)
        if self._last_check is None:
            self._last_check = now
            return

        import stores

        for sid, schedule in list(stores.schedules.items()):
            if not schedule.enabled:
                continue
            if _should_fire(schedule.cron_expression, self._last_check, now):
                try:
                    await self._fire_schedule(sid, schedule)
                except Exception as exc:
                    logger.warning("Failed to fire schedule %s: %s", sid, exc)

        self._last_check = now

    async def _fire_schedule(self, sid: str, schedule: object) -> None:
        import stores

        t = datetime.now(UTC)
        stores.schedules[sid] = schedule.model_copy(  # type: ignore[attr-defined]
            update={"last_run": t, "updated_at": t}
        )
        logger.info("Schedule %s fired: %s", sid, schedule.name)  # type: ignore[attr-defined]

        template_id = schedule.mission_template_id  # type: ignore[attr-defined]
        if not template_id:
            return

        from routes.audit import log_audit

        log_audit("schedule_fire", "system", target=sid, detail={"name": schedule.name})  # type: ignore[attr-defined]


def _should_fire(cron_expr: str, last: datetime, now: datetime) -> bool:
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return False
    minute, hour, day_month, month, day_week = parts
    checks = [
        _field_matches(minute, now.minute, 0, 59),
        _field_matches(hour, now.hour, 0, 23),
        _field_matches(day_month, now.day, 1, 31),
        _field_matches(month, now.month, 1, 12),
        _field_matches(day_week, now.weekday(), 0, 6),
    ]
    if not all(checks):
        return False
    delta = now - last
    if delta < timedelta(minutes=1):
        return False
    return True


def _field_matches(field: str, value: int, low: int, high: int) -> bool:
    if field == "*":
        return True
    if "," in field:
        return any(_field_matches(f.strip(), value, low, high) for f in field.split(","))
    if "/" in field:
        base, step = field.split("/", 1)
        step_val = int(step)
        if step_val <= 0:
            return False
        start = low if base == "*" else int(base)
        return value >= start and (value - start) % step_val == 0
    if "-" in field:
        lo, hi = field.split("-", 1)
        return int(lo) <= value <= int(hi)
    return int(field) == value
