# Stream 4 Checkpoint 15: Canvas Entrypoints and Readiness Levels

Date: 2026-08-14
Source audited: `develop`

This checkpoint distinguishes three different Canvas surfaces that currently have different reachability/wiring status. Treating all of them as equally live would produce the wrong Stream 7 migration order.

## 1. Hive optional Canvas route is live but narrow

Hive optionally mounts `routes.canvas` at `/v1/canvas`.

The route exposes:

- the hardcoded Canvas/Davinci DAG definition
- visual-quality evaluation
- hill-climb status

It does **not** expose an endpoint that actually runs `CanvasHillClimber.run_pass()` in the current route file.

Classification: `live definition/eval/status adapter`.

## 2. Hive Canvas visual eval directly invokes LiteLLM

`services.canvas_dag.visual_quality_eval()` builds and sends a chat-completion request directly to LiteLLM using environment configuration.

That is another live/direct provider Invocation path outside canonical Binding/Invocation.

### Stream 6 handoff

Preserve the visual-judge domain contract but migrate managed platform model calls onto canonical Provider/Invocation.

## 3. Hive Canvas DAG is product/template behavior, not canonical execution

`CANVAS_DAG` defines a specialized visual pipeline:

- style interpreter
- composition planner
- generator
- compositor
- critic
- refiner

with visual-quality eval and hill-climbing intent.

This is useful product GraphTemplate source material.

It should not keep a second graph execution backend.

## 4. maistro-server mounts a larger `/v2/canvas` domain boundary

`maistro_server.api.canvas` exposes authenticated Canvas design operations:

- list/create/get/update/soft-delete designs
- list layers with design detail
- image export through an injected compositor
- asset listing through an injected registry
- optional design mutation events
- explicit versioned content negotiation

Publish is explicitly 501 because the canvas ability exposes no publish operation.

Classification: `mounted Canvas domain/control-plane boundary`.

## 5. The standard maistro-server entrypoint does not wire required Canvas dependencies

The Canvas router requires `app.state.canvas_store`; without it every design route returns 503.

Optional capabilities require:

- `app.state.canvas_compositor`
- `app.state.canvas_events`
- `app.state.canvas_asset_registry`

`maistro_server.main` mounts the Canvas router and documents that deployments must inject these objects, but the standard entrypoint itself does not set them during lifespan/startup.

### Truth-status consequence

The API route is structurally reachable, but the standard source entrypoint does not by itself make Canvas design CRUD operational.

External deployment composition may inject the dependencies, so this is **not** proof no production environment wires Canvas. It is proof the repo's standard app bootstrap does not own that wiring.

Classification: `mounted boundary with external/injected operational dependency`.

## 6. Private Canvas generation job runner remains structurally unreachable

The current reachability ratchet lists Canvas runner/store/tool generation modules as unreachable.

Earlier Stream 4 audit identified the useful private job behavior:

- atomic claim
- worker lease
- lease reaping
- retries/requeue
- cancellation
- generation/refine/reference/variant domain rules

That runner is not the backing lifecycle for maistro-server `/v2/canvas` today.

Classification: `unreachable generation/recovery behavior source`.

## 7. Canvas migration should therefore be staged by actual current path

### Current live/product-visible source material

- Hive Canvas DAG definition + eval/status
- maistro-server versioned domain API contract
- Canvas store/compositor protocol boundary

### Requires wiring decision

- where CanvasStore/compositor/asset registry are instantiated in the canonical deployment composition
- how Canvas design ownership maps onto canonical Workspace/Project
- how mutation events map onto canonical Event

### Unreachable behavior to selectively port

- generation job execution
- claim/lease/retry/recovery
- generator/refiner provider invocation

## 8. Canvas domain ownership is currently owner/org based, not canonical Project based

maistro-server uses authenticated principal user ID as `org_id` for Canvas store list/create/require checks.

That is a working isolation rule, but it is not yet canonical Workspace/Project ownership/resource authorization.

### Stream 3/7 handoff

Preserve user isolation during migration. Decide whether Canvas designs become Project resources, Workspace resources, or a product-owned subtree under Project rather than silently equating `org_id` with canonical Workspace.

## 9. Canvas events are optional and can currently be no-op

maistro-server Canvas mutation routes call an injected `canvas_events` callback when present. If absent, design.created/updated/deleted emission is a no-op.

This is another producer Stream 2 can normalize onto canonical Event without forcing Canvas to own an event bus.

## 10. Canvas publish is explicitly not implemented

The v2 publish route returns 501 and notes print-on-demand lives outside the engine.

Do not treat publish as a migration-parity requirement unless Stream 7 explicitly adopts that external product capability into MAIstro.

## Immediate handoffs

### Stream 2

Canvas design mutation events should become canonical Event projections where desired; optional callback/no-op behavior is the current baseline.

### Stream 3

Map current user/org design isolation onto explicit canonical resource ownership rather than assuming existing `org_id` has canonical meaning.

### Stream 6

Migrate Hive visual eval and any future generation/provider calls onto canonical Invocation.

### Stream 7

Do not lump Canvas into one binary live/dead classification. Preserve the v2 domain contract and visual-pipeline domain behavior first; wire canonical store/resource ownership; selectively port the unreachable generation job mechanics when generation becomes part of the canonical product path.

## Reachability lesson

Mounted route != operational feature when required app-state dependencies are not constructed by the standard entrypoint. Dependency injection is part of reachability for behavior, not just import reachability.
