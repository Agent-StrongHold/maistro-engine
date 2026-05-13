---
id: S-143
title: "1kHz reactor loop — event-driven runtime, replaces 30-min heartbeat"
domain: conductor
status: draft
priority: P1
effort: ""
created: 2026-04-25
completed: ""
owner: conductor
commits: []
supersedes: "S-001 (heartbeat becomes a degenerate event source on the reactor)"
---

# S-143: 1kHz Reactor Loop

## Problem

The original heartbeat (S-001) runs at 30-minute cadence: a wall-clock tick wakes the conductor, it scans `HEARTBEAT.md` for action items, decides whether to act or return `HEARTBEAT_OK`, and goes back to sleep. This was right as a bootstrap pattern — it gave the conductor *some* sense of time — but it wedges the architecture into a polling shape that doesn't fit the actual product:

- **Background work is event-driven.** Mood Ring (S-031) wants to react to system-health changes as they happen, not 30 minutes later. Phantom (S-030) wants to fire when a skill changes, not on the next tick. Federation (S-156) wants to handle incoming Lightning messages immediately. "Wait for the next 30-minute heartbeat" is the wrong default.
- **Latency on heartbeat-spawned tasks is 30 min average.** A reminder set for 14:01 fires at the 14:30 tick. Time Capsule (S-034) and Morning Digest (S-011) work around it with their own scheduling, but each is a separate cron-shaped subsystem.
- **The capability envelope (S-002–S-005) is decoupled from scheduling.** Heartbeat-spawned tasks (S-105) get an extended tool-call cap *because* heartbeat is special. With a reactor loop, every event source uses the same envelope construction; "who fired this and what cap do they get" is per-source policy, not heartbeat-vs-chat.

## Solution

Replace the 30-minute polling heartbeat with a **1kHz event-driven reactor loop** — epoll on Linux, kqueue on macOS, IOCP on Windows. Every background subsystem becomes an event source on the reactor. The 30-minute wall-clock tick becomes one event source among many; "heartbeat" persists as a name for that specific tick but is no longer the runtime's primary cadence.

### Reactor architecture

```
  Event sources                     Reactor                  Handlers
  -------------                     -------                  --------
  wall-clock ticks (cron-like)  ───▶
  filesystem watches (inotify)  ───▶
  network: HTTP / LN keysend     ───▶                         construct AgentSpec
  IPC: subsystem signals          ───▶ [event loop]   ────▶ (S-002..005), spawn,
  skill-trigger events           ───▶   ~1kHz cycle           run, log to audit
  user prompt arrival             ───▶                         (S-152), submit state
  federation incoming             ───▶                         writes (S-140)
  GPU / system-health signals    ───▶
```

**1kHz** here means *the loop checks for ready events at most once per millisecond*; quiescent periods sleep on the kernel wait, no busy spin. "1kHz" is the upper bound on latency from event-ready-on-fd to handler-invoked, not a steady-state work rate. Steady-state CPU under no load is near zero.

## Acceptance Criteria

- [ ] Reactor loop wakes within 5ms p95 of an event becoming ready
- [ ] All existing heartbeat behavior (S-001) works as a `wall-clock-tick:30m` event source on the reactor
- [ ] Quiescent CPU usage < 1% on a typical desktop
- [ ] Multiple event sources can fire concurrently without race conditions; test with a deliberately racing pair (network + wall-clock + filesystem)
- [ ] Each source declares its capability-envelope policy at registration; spawner uses that policy to construct the AgentSpec
- [ ] No event source bypasses the Bouncer; every event payload is screened before the handler runs
- [ ] All state mutations from handlers go through `state.submit()` (S-140); no direct write-mode SQLite connections
- [ ] Reactor handlers cannot block the loop — long-running handler work is offloaded to a worker pool; handler return must be ≤5ms p95
- [ ] Telemetry: per-source event count and latency visible in the Console
- [ ] Failing handler does not crash the reactor; reactor logs the error and continues
- [ ] SIGTERM shutdown: reactor stops accepting new events, drains in-flight handlers within a configurable grace period (default 5 s), cancels remaining work and rolls back any partial state writes, then runs a WAL checkpoint (S-140) before exit
- [ ] Backpressure: when `state.submit()` queue depth exceeds the configured limit (default 10,000 items), the reactor pauses event delivery from the highest-volume sources rather than dropping events; handlers unable to submit state within the backpressure timeout (default 1 s) emit a `REACTOR_BACKPRESSURE_EVENT` alert
