---
id: SPEC-070226-b234
title: "Events, triggers, and the reactor: durable event log with idempotent replay"
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-07-02
substrate:
  - maistro-engine#ADR-086
  - maistro-engine#ADR-037
  - maistro-engine#SPEC-013
implements:
  - maistro-engine#ADR-086
related:
  - maistro-engine#ADR-082
supersedes: []
blocks: []
blocked-by: []
contracts:
  - behavioral
  - boundary
tests: []
layer: Observability
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-070226-b234: Events, triggers, and the reactor — durable event log with idempotent replay

## Context

ADR-086 specifies a durable event log (PostgreSQL table of immutable events) and trigger+handler
model: operators define triggers ("on agent.delegated, run X"), the reactor processes events,
and handlers are replayed durably (idempotent, no lost events on crash).

The 1kHz reactor loop (SPEC-013) currently emits events in-memory; this SPEC persists them.

## Goals

- Durable event log (all events persisted to PostgreSQL).
- Trigger definitions (declarative; stored in config or registry).
- Event processing and handler invocation (async queue, batched).
- Idempotent replay (if reactor crashes mid-handler, resume without duplication).
- Audit trail (all events searchable, never deleted).

## Non-goals

- Event streaming to external systems (Kafka, Pub/Sub; Phase 2).
- Learned trigger optimization (operator-configured for Phase 1).

## Decision

### Event log schema

```sql
CREATE TABLE event_log (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(255),  -- "agent.created", "task.completed", etc.
    entity_type VARCHAR(100),  -- "agent", "task", "design"
    entity_id VARCHAR(255),
    payload JSONB,  -- event-specific data
    source VARCHAR(100),  -- "core", "security", "resilience"
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX (event_type, created_at)
);

CREATE TABLE trigger_definitions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    event_pattern VARCHAR(255),  -- glob: "agent.*" matches "agent.created", "agent.delegated"
    handler_url VARCHAR(1024),  -- HTTP endpoint to call
    enabled BOOLEAN DEFAULT true
);

CREATE TABLE handler_invocations (
    id SERIAL PRIMARY KEY,
    trigger_id INTEGER,
    event_id INTEGER,
    status ENUM('pending', 'success', 'failed', 'retrying'),
    attempts INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (trigger_id, event_id)  -- idempotency key
);
```

### Reactor event processing

```python
class Reactor:
    """1kHz loop that processes events and invokes handlers."""
    
    async def process_events(self):
        """Called every 1ms by the event loop."""
        # Fetch unprocessed events
        pending_events = await event_log.get_pending(limit=100)
        
        for event in pending_events:
            # Find triggers that match
            triggers = await trigger_store.get_matching(event.event_type)
            
            for trigger in triggers:
                # Check if already invoked (idempotency)
                invocation = await invocation_store.get(trigger.id, event.id)
                if invocation and invocation.status == "success":
                    continue
                
                # Invoke handler (async, with retry)
                if not invocation:
                    invocation = await invocation_store.create(trigger.id, event.id)
                
                try:
                    await self.invoke_handler(trigger, event)
                    invocation.status = "success"
                except Exception as e:
                    invocation.attempts += 1
                    invocation.last_error = str(e)
                    if invocation.attempts < 3:
                        invocation.status = "retrying"
                    else:
                        invocation.status = "failed"
                        emit("handler.failed", trigger=trigger.name, event=event.id)
                
                await invocation_store.save(invocation)
    
    async def invoke_handler(self, trigger: TriggerDefinition, event: Event):
        """HTTP POST the event to the handler endpoint."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                trigger.handler_url,
                json=event.to_dict(),
                timeout=5.0
            )
            if response.status_code >= 400:
                raise HTTPError(f"{response.status_code}: {response.text}")
```

### Trigger definitions (YAML)

```yaml
triggers:
  - name: "log-delegations"
    event_pattern: "agent.delegated"
    handler_url: "http://localhost:8000/handlers/log"
    
  - name: "notify-on-task-failure"
    event_pattern: "task.failed"
    handler_url: "http://localhost:8000/handlers/notify"

  - name: "update-cache-on-memory-write"
    event_pattern: "memory.written"
    handler_url: "http://localhost:8000/handlers/cache-update"
```

### Idempotency guarantee

The `(trigger_id, event_id)` unique key ensures a handler is invoked at most once per event:
- If a handler crashes mid-execution, the invocation status is "retrying".
- On reactor restart, the handler is retried (same invocation row).
- If the handler succeeds (status="success"), it's skipped on any future replay.

## Acceptance criteria

- [ ] Every event emitted is persisted to event_log (property: no lost events).
- [ ] Triggers match event patterns correctly ("agent.*" matches "agent.created" but not "task.created").
- [ ] Handler is invoked exactly once per event (idempotency test: simulate crash, restart, confirm
      no duplicate invocations).
- [ ] Failed handler is retried up to 3 times (exponential backoff).
- [ ] Event query API (GET /events?event_type=...&since=...) returns paginated results.

## Testing

- Unit: trigger pattern matching, idempotency key logic.
- Integration: emit event, handler invoked; crash reactor mid-handler, restart, confirm handler
  completed without duplication.
- Property: "every event in log is processed by all matching triggers exactly once" (Hypothesis).
- Load: 1000 events/second, 10 triggers, verify no dropped events.

## References

- [ADR-086: Events, Triggers, Reactor](../adr/ADR-086-events-triggers-reactor.md)
- [SPEC-013: Reactor loop](SPEC-013-reactor-loop.md)
