# Stream 4 Checkpoint 16: Live Design Path, Isolation, and Render Jobs

Date: 2026-08-14
Source audited: `develop`

This checkpoint traces Hive's mounted Design product path. It finds a live domain service, another private job lifecycle, a likely disconnected render edge, and an important current resource-isolation gap.

## 1. Design is a live Hive product/service

Hive lifespan calls `start_design_service(settings)` and initializes:

- DesignEngine
- built-in Design skills
- Design system registry
- optional PostgreSQL DesignProjectStore
- RendererRegistry
- optional OpenDesign provider discovery
- preview/render services

Mounted `/v1/design` routes expose:

- create/list/get design projects
- skill discovery/catalog
- render-job create/status

Classification: `live Design product/domain surface`.

## 2. Design Project is another product-specific Project noun

`maistro_design` DesignProject represents generated design work/output, not canonical ownership Project.

The Hive routes expose it under `/design/projects` and the Design store persists it independently.

### Stream 7 naming constraint

Do not migrate DesignProject into canonical Project merely because of the noun. It is a Design artifact/work item/resource that should live **under** a canonical Project/Workspace ownership scope if retained.

## 3. Current Design org resolution falls back to one shared `default-org`

`routes/design._get_org_id()` returns `request.state.org_id` when present; otherwise it returns the literal `default-org`.

Its TODO says auth-context org extraction is not yet wired.

The live Hive AuthMiddleware sets `request.state.user` for authenticated `/v1/*` requests. It does not set `request.state.org_id`.

On the standard Hive request path, Design create/list therefore use `default-org` unless some external/custom middleware adds org_id.

Classification: `live resource-isolation compatibility gap`.

## 4. Fetch-by-ID does not enforce org ownership

`GET /design/projects/{project_id}` calls `store.get(project_id)` and returns the project when found.

It does not compare the fetched project's org_id to the caller's resolved org/user scope.

The route is authenticated by Hive's outer middleware, but authenticated users are not object-scoped here.

### Stream 3 priority handoff

Design project access should be moved under canonical resource authorization. At minimum, current product parity needs owner/org isolation across list/get/render operations.

Do not rely on route obscurity or project IDs as access control.

## 5. Design generation bypasses canonical Run

`POST /design/projects` calls `DesignEngine.generate(...)` directly and returns the resulting DesignProject.

The route describes a generation pipeline (validate skill/design system, Warden scan, prompt assembly, persistence), but execution is not represented as canonical Run/NodeRun/Attempt/Invocation/Event.

### Stream 1/6/7 direction

Keep Design discovery/prompt/render domain behavior. When generation involves model/provider execution, expose it through canonical execution primitives rather than retaining a private product execution lifecycle.

## 6. RendererRegistry is another provider registry domain

DesignService creates a `maistro_design.renderers.RendererRegistry`, optionally registers OpenDesignProvider, performs discovery, and uses filled renderer slots to determine which Design skills are available.

This is useful Design-specific provider capability behavior.

### Stream 6 constraint

Do not blindly delete it in favor of core CapabilityRegistry. Decide whether renderer providers should adapt into canonical Capability/Provider or remain a domain registry whose external calls are represented by canonical Invocation.

Preserve skill-availability behavior based on discovered renderer slots.

## 7. Render jobs own another private lifecycle

`DesignPreviewService.RenderJob` tracks:

- job_id
- project_id
- format
- status
- URL
- error
- timestamps

Statuses are documented as pending/rendering/completed/failed.

Jobs live in an in-memory dictionary.

Classification: `live product job DTO / duplicate universal lifecycle`.

## 8. Render-job creation does not itself dispatch rendering

`POST /design/projects/{project_id}/render`:

- fetches the Design project
- validates output format
- calls `preview_svc.create_render_job(...)`
- returns the pending job

`create_render_job()` only inserts a pending RenderJob into `_render_jobs`.

The standard Hive startup initializes DesignPreviewService and DesignRenderService but does not start a render-job worker in the code traced for this checkpoint.

The mounted Design route provides only create-job and poll-job endpoints; no processing endpoint is present in the route file.

### Classification

`reachable render job API with execution edge not found in standard startup/route path`.

This is strong evidence of a disconnected feature, but before deletion or behavior claims Stream 4 should still treat an external/background caller outside the standard path as theoretically possible.

## 9. Rendering methods exist independently of the job dispatcher

DesignPreviewService contains `render_to_pdf`, `render_to_pptx`, and `render_to_docx`, delegating to DesignRenderService.

So the rendering capability exists; the missing link is the pending-job consumer/dispatcher in the standard product path, not absence of render implementation.

### Stream 7 migration opportunity

This maps cleanly to:

`Design render request -> canonical Run/Node/Attempt -> renderer Invocation -> artifact`

rather than reviving a bespoke in-memory render worker.

## 10. Design persistence gracefully degrades when DATABASE_URL is absent

DesignService initializes PostgreSQL project persistence only when DATABASE_URL is configured.

- list returns empty when store unavailable
- fetch/render paths can return 503/runtime errors depending on route
- DesignEngine itself can still initialize without project store

This is intentional deployment behavior worth keeping explicit during migration.

## Immediate handoffs

### Stream 1

Design generation/render jobs should become canonical execution consumers where they perform work; Design domain records remain specialized resources/artifacts.

### Stream 2

Design generation/render lifecycle should emit canonical Event/Checkpoint rather than rely only on product job dictionaries if migrated to Run.

### Stream 3

High priority: fix/migrate Design resource isolation. Standard AuthMiddleware does not set org_id, routes fall back to shared `default-org`, and fetch-by-ID lacks org ownership verification.

### Stream 6

Reconcile Design RendererRegistry/provider execution with canonical Provider/Invocation while preserving renderer-slot availability semantics.

### Stream 7

Preserve Design skills/systems/discovery/output domain behavior. Rename/project DesignProject as a product resource under canonical ownership rather than a competing canonical Project. Replace private render-job lifecycle with canonical execution once the dispatcher is connected.

## Reachability lesson

A live service can have both correctly wired domain operations and disconnected sub-workflows. Design generation is live; render job submission/status is live; a standard render-job consumer was not found. Audit should classify those edges independently rather than assigning one readiness label to the package.
