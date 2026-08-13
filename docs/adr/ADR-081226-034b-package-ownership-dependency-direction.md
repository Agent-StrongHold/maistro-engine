# ADR-081226-034b: Package Ownership and Dependency Direction

- **Status:** Accepted
- **Date:** 2026-08-12
- **Deciders:** MAIstro maintainers
- **Technical Area:** Package boundaries, dependency direction, architecture governance

## Context

The ecosystem audit confirms that MAIstro's package boundaries are useful but historical responsibility has drifted. Some product packages own orchestration that belongs in canonical core services, `maistro-bootstrap` contains both bootstrap and user-work execution pieces, and the package currently named `maistro-registry` is architecture/spec governance tooling rather than a runtime registry.

Convergence must clarify semantic ownership without forcing every specialized capability into `maistro-core`.

## Decision

### Core dependency direction

`maistro-core` is the authoritative home for reusable MAIstro domain semantics and generic platform mechanisms.

Product/application/specialized packages depend inward on core contracts. Core MUST NOT depend on Hive, server UI/application code, Canvas, Design, Turing, RSI, Evolve or other specialized product packages to define canonical semantics.

Conceptually:

```text
surfaces/products/specialized packages
              |
              v
         maistro-core
              |
              v
   ExecutionRuntime mechanics
```

ExecutionRuntime may live in core but remains a mechanics boundary and MUST NOT import graph/product semantics to decide them.

### `maistro-server`

`maistro-server` is the generic API/application transport surface over canonical services. It may host adapters/routes for optional specialized packages, but transport handlers do not become domain lifecycle owners and should not call provider implementations directly when canonical services exist.

### `hive-conductor`

Hive is a product/application consuming canonical MAIstro services. Hive-specific UX, data and integrations remain Hive-owned. Duplicate graph/task/schedule/runtime lifecycle ownership migrates to core services behind compatibility adapters.

### Specialized domain packages

`maistro-canvas`, `maistro-design`, `maistro-turing`, `maistro-evolve` and `maistro-rsi` remain specialized packages. They may provide NodeTypes, Personas/surfaces, templates, capabilities/providers, policies and domain assets through public extension contracts.

They do not redefine Workspace/Run/NodeRun/Attempt or bypass canonical permissions/events.

### Builders

Builders remains a product/domain capability and set of surfaces, even where code currently lives inside core/bootstrap. Its worker/workflow behavior maps to Persona, templates, Graph/Node and canonical Run services rather than a parallel universal runtime.

### `maistro-bootstrap`

`maistro-bootstrap` owns installation, detection, planning/resolution, materialization, setup wizard/configuration and environment/provider initialization concerns.

Current Builders agent loop, model selection, sandbox/container execution, runtime session, delivery and execution credential behavior must be mapped/migrated to canonical owners where those paths perform user work. Physical moves follow parity tests; they are not required in one rename commit.

### Architecture governance package

The semantic target name for the current ADR/spec parser/linker/validator/generator package is **`maistro-arch-governance`** because it governs architecture artifacts and fitness rather than runtime registries.

Target names:

```text
package/distribution: maistro-arch-governance
Python import:         maistro_arch_governance
CLI:                   maistro-arch
```

The physical rename is intentionally deferred until imports, root workspace metadata, lockfile, compatibility and CI can be changed/tested together in a mechanically isolated migration commit.

Runtime/domain registries remain explicitly named by semantics, e.g. NodeTypeRegistry, TemplateRegistry, CapabilityRegistry, ProviderRegistry, ModelRegistry and ArtifactRegistry. There is no requirement for one generic Registry abstraction.

### Extension over reverse dependency

Core discovers specialized implementations through explicit registration/entry-point/adapter contracts. A need for Canvas/Turing/Design behavior MUST NOT be solved by adding a core import of that package.

### Physical package changes follow semantic convergence

Rename/move/split work requires:

1. locked semantic owner;
2. known import/dependency impact;
3. compatibility plan;
4. behavior/reachability tests;
5. mechanically isolated changes where practical.

## Consequences

- Strong domain packages remain independent and reusable.
- Core stops accumulating product-specific UX semantics.
- Product packages progressively lose duplicate lifecycle authority.
- Architecture fitness can enforce dependency direction.
- The governance package name no longer collides conceptually with runtime registries once the physical rename lands.

## Compliance

A package change complies when canonical domain semantics flow from core, specialized packages extend through public contracts, product/server layers do not become lifecycle authorities, Runtime does not decide domain semantics, and dependency direction does not require core to import outward product packages.

## References

- `ADR-081226-9944`
- `ADR-081226-69ee`
- `docs/analysis/ECOSYSTEM-INVENTORY.md`
- `docs/analysis/PACKAGE-OWNERSHIP-DECISIONS.md`
