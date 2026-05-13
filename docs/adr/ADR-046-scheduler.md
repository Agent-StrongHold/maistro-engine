# ADR-046: Scheduler — Recurring agent tasks

**Status:** Proposed
**Date:** 2026-05-13
**Depends on:** ADR-018 (Task Record Persistence), ADR-021 (Conductor Seed)

---

## Context

`src/maistro/scheduler/` exists as an empty package. Product repos (Project_mAIstro household automations, AgentTuring autonoetic-loop reflections) need recurring agent invocations — "every weekday at 7am, run the morning briefing", "every 15 min, poll the inbox". Today they would have to roll their own cron-runner per product, duplicating queue-submission, retry, and observability code that already lives in `TaskQueue` / `conductor.py`.

Hermes-desktop ships this as a first-class user feature: `src/renderer/src/screens/Schedules/Schedules.tsx` + `src/main/cronjobs.ts` give frequency presets (minutes / hourly / daily / weekly / custom cron), pause/resume/trigger-now, `last_status`, `last_error`, repeat counter, and per-job skill selection. The patterns transfer cleanly to a substrate API.

## Problem

No first-class "schedule a recurring agent task" primitive. Each product reinvents cron + retry + status surfacing.

## Solution sketch

A `Schedule` model + worker that re-submits to the existing `TaskQueue` on cron fire. Reuses `TaskResponse` for `last_run` / `last_error` surfacing — no new status taxonomy. Single APScheduler `AsyncIOScheduler` instance owned by the conductor process, schedules persisted in Postgres via Alembic migration.

Lifecycle:

1. `POST /v1/schedules` writes row, registers job with APScheduler.
2. On fire, worker constructs a `TaskCreate` from the schedule's `task_template` and submits to `TaskQueue`. Schedule row's `last_task_id` updated.
3. `last_status` / `last_error` derived from joining the resulting `TaskRecord` (no schedule-local status duplication).
4. Pause flips `enabled=false` and removes the APScheduler job; resume re-registers.
5. Trigger-now submits a one-off task without altering the schedule cadence.

## Data model (sketch)

```python
class Schedule(Base):
    id: UUID                         # primary key
    profile_id: str                  # tenant/profile scoping
    name: str                        # human label
    cron: str                        # standard 5-field cron, UTC
    timezone: str = "UTC"            # IANA tz, applied to cron
    task_template: dict              # frozen TaskCreate payload
    enabled: bool = True
    max_runs: int | None             # repeat counter cap; None = unlimited
    runs_so_far: int = 0
    last_task_id: UUID | None
    last_fired_at: datetime | None
    created_at: datetime
    updated_at: datetime
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/schedules` | Create schedule |
| `GET` | `/v1/schedules` | List (filterable by `profile_id`, `enabled`) |
| `GET` | `/v1/schedules/{id}` | Detail, includes `last_status` from joined `TaskRecord` |
| `PATCH` | `/v1/schedules/{id}` | Edit cron / template / enabled |
| `DELETE` | `/v1/schedules/{id}` | Remove |
| `POST` | `/v1/schedules/{id}/pause` | Convenience: set `enabled=false` |
| `POST` | `/v1/schedules/{id}/resume` | Convenience: set `enabled=true` |
| `POST` | `/v1/schedules/{id}/trigger` | One-off run, returns `task_id` |

## Acceptance criteria

- [ ] Creating a schedule with cron `*/5 * * * *` produces a `TaskRecord` every 5 min for at least 3 cycles in a 20-min integration test.
- [ ] Pause stops fires within one cycle; resume restarts on next cron tick.
- [ ] `max_runs` enforced — schedule auto-disables after Nth fire.
- [ ] On conductor restart, all `enabled=true` schedules re-register from Postgres before accepting traffic.
- [ ] Prometheus counter `maistro_schedule_fires_total{schedule_id, outcome}` increments on each fire.
- [ ] OTel span `schedule.fire` parents the resulting `task.run` span via the existing `@trace_agent` decorator.

## Open questions

1. **Per-schedule concurrency policy.** If a schedule fires while its previous task is still running, do we (a) skip, (b) queue anyway, (c) cancel-previous? Hermes does (b). Recommend (a) as the default with an `overlap_policy` enum field.
2. **Multi-process deployments.** APScheduler in-memory works for the single-conductor case. For multi-replica deploys, do we need a Postgres-advisory-lock leader, or is that ADR-future scope?
3. **Time-zone semantics on cron.** Store as IANA tz string on the row and apply at fire time, or normalize to UTC at create time? Hermes stores user-local. Recommend IANA-on-row to keep DST handling correct.
4. **Skills-per-schedule (hermes feature).** Defer to `task_template` carrying skill ids — don't add a separate column unless skill-policy diverges from task-policy.

## Source references

- `hermes-desktop:src/renderer/src/screens/Schedules/Schedules.tsx` — UX surface (frequency presets, pause/resume/trigger-now, repeat counter, last_error)
- `hermes-desktop:src/main/cronjobs.ts` — in-process cron runner
- `maistro-engine:src/maistro/scheduler/` — empty target package
- `maistro-engine:src/maistro/tasks/runner.py`, `tasks/queue.py` — reused submission path

## Out of scope

- Multi-replica leader election (revisit when conductor goes horizontal).
- UI — substrate exposes API only; product repos own the schedules screen.
- Backfill / catch-up after long downtime — missed fires are dropped.
