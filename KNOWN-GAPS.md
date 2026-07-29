# Known Gaps

This document is the source for the v1.0.0 release notes' "Known
limitations" section. Each item below is shipped surface area whose current
behavior is intentionally limited or degraded. The entries are v1.1 tracking
inputs, not promises that the capability is complete in v1.

## Deferred To v1.1

### Task queue persistence

The task queue is in memory. A process restart discards queued and active task
state; it does not recover tasks from durable storage.

Tracking: implement the persistence and recovery design in
[ADR-018](docs/adr/ADR-018-task-record-persistence.md).

### Canvas background job runner

Canvas jobs can be created, but they do not advance unless an external runner
is configured and operating. The shipped service does not provide a built-in
worker that consumes those jobs.

Tracking: add the runner described by SPEC-203 before treating canvas jobs as
self-progressing work.

### Canvas publish and export

The Canvas publish endpoint returns `501` because print-on-demand integration
lives outside this repository. PDF and SVG export also return `501`; PNG
export requires a configured compositor and otherwise returns `501`.

Tracking: implement publish and export integrations as a v1.1 capability.

### Conductor degraded modes

The Conductor can continue in a degraded state when optional services are
unavailable. Startup now makes optional-router failures observable, but the
degraded state is not yet a complete user-facing operating mode.

Tracking: finish the visible degraded-mode behavior in [F3](https://github.com/BlakeMatthews-dev/maistro-engine/issues/302).

### Canvas Studio cutover

The engine mounts `/v2/canvas` routes, but the separate Canvas Studio frontend
has not completed its migration to that API. The `/v2` surface is therefore
not the end-to-end production boundary for Studio yet.

Tracking: complete the cutover described by
[SPEC-070226-8239](docs/specs/SPEC-070226-8239-canvas-studio-cutover.md).

### HTTP API content negotiation

[ADR-076](docs/adr/ADR-076-http-api-versioning.md) is not implemented across
the business API. Canvas has a narrow `/v2` response-format mechanism, but
the business routes remain mounted under `/v1` and do not provide the ADR's
general content-negotiation scheme.

Tracking: implement ADR-076's API-wide version negotiation in v1.1.

## Release-Notes Text

The following text is intended to be copied verbatim into the release notes.

> v1.0.0 ships with an in-memory task queue, so a restart loses queued and
> active tasks. Canvas jobs require an external runner; Canvas publish and
> some export formats are not implemented. Conductor can run in degraded mode
> when optional services are unavailable. Canvas Studio has not completed its
> `/v2/canvas` cutover, and API-wide HTTP content negotiation from ADR-076 is
> deferred to v1.1.
