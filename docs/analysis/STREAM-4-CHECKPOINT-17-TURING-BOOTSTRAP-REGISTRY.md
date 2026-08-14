# Stream 4 Checkpoint 17: Turing, Bootstrap, and Registry

Date: 2026-08-14
Source audited: `develop`

This checkpoint classifies three remaining ecosystem packages without changing canonical architecture.

## Turing

### Product boundary

`packages/maistro-turing/backend/main.py` is a real standalone FastAPI product service. It mounts health, auth, state, feed, chat, and admin routes on its own process/port and imports the `maistro_turing` library. Turing therefore should not be flattened into a generic benchmark/evaluation package.

### Live runtime shape

The active implementation is `maistro_turing.runtime` from `runtime/__init__.py`. It defines:

- `TuringConfig`
- `TuringActor`
- `TuringChatSession`
- bridge-based memory/security/provider/classifier integration

The sibling flat file `src/maistro_turing/runtime.py` explicitly declares itself DEAD CODE. Python resolves the sibling package directory first, and the implementation was already copied into `runtime/__init__.py`. This is a strong deletion candidate after confirming no file-path tooling/tests intentionally read the inert source file.

### Current production-readiness gaps

The standalone backend's `TuringState` is process-local and in-memory. It constructs `TuringMemoryBridge`, `TuringSecurityBridge`, `TuringProviderBridge`, and `TuringClassifierBridge` without backing maistro-core implementations. As documented in that file:

- memory writes are dropped without stores
- security scans pass through when Warden is absent
- provider calls have no LLM client
- classifier falls back to generic classification

The mounted chat route guards the absent provider and returns 503. Its sessions are also process-local in-memory state keyed by `(user_id, session_id)`.

This means the Turing API is reachable, but several advertised integrations are adapter seams rather than fully wired production behavior.

### Canonical migration classification

Keep Turing-specific domain behavior:

- self-model / facets / mood
- cognition and producer behavior
- artifact kinds such as blog/reflection/curiosity/emotion
- Turing-specific chat identity and UX

Converge shared services:

- `TuringProviderBridge` -> Stream 6 Binding/Provider/Invocation integration
- `TuringMemoryBridge` -> canonical hierarchy-aware memory service
- `TuringSecurityBridge` -> live security/runtime policy path
- Turing chat session persistence -> canonical Session where appropriate
- producer artifacts -> canonical Artifact/Event projections where appropriate

Do not turn Turing's self-model or cognition domain into universal Run state.

### Turing provider note

`TuringProviderBridge` maps Turing `PoolConfig` to a maistro-core LLM client and owns a synchronous wrapper that may create a thread pool to run an async completion when already inside an event loop. Preserve pool/domain selection semantics, but Invocation should own actual model-call execution mechanics after Stream 6 convergence.

## Bootstrap

`maistro-bootstrap` is installation/platform lifecycle, not user workload lifecycle.

Its documented responsibilities are:

- interactive or YAML install planning
- feature-slice / compose-addon selection
- structured install-plan generation
- platform detection and command materialization
- optional compose build application

The README explicitly states that `--apply` performs compose build only and that container startup remains a separate operator action.

Classification:

- keep outside canonical Run/NodeRun/Attempt
- treat install plan/schema/resolver/platform detection as control-plane/bootstrap behavior
- connect provider/environment initialization to canonical registries where useful
- do not model install/bootstrap operations as ordinary Workspace product Runs unless a future explicit user-work execution requirement emerges

The `builders` subpackage must continue to be classified separately because Builders itself contains product execution semantics already covered by earlier Stream 4 checkpoints.

## Registry

`maistro-registry` is documentation/governance tooling, not the runtime Capability/Provider/Template/Artifact registry.

Its own package contract is:

- validate ADR/spec front matter
- validate/link cross-references
- generate the canonical ADR/spec registry
- expose this through the `maistro-registry` console script

Classification:

- retain as repository governance/build tooling
- do not merge it with CapabilityRegistry, template registries, model registries, or artifact registries merely because they share the word `registry`
- its DAG/linker/generator/parser/schema/validator modules operate on documentation metadata, not product execution objects

## Cross-stream handoffs

### Stream 6

Turing provider/security bridge behavior is useful adapter input, but actual LLM calls should converge through canonical Binding/Invocation rather than preserving a second pool-driven execution path.

### Stream 7

Turing should remain a specialized product/domain adapter. Preserve its self-model/cognition/producer/chat semantics while replacing generic provider/memory/security/session/artifact plumbing with canonical services.

Bootstrap and maistro-registry should remain outside normal product execution migration except for narrow integration seams.

## Delete-after candidate

Strong candidate:

`packages/maistro-turing/src/maistro_turing/runtime.py`

Prerequisites before deletion:

1. confirm no scripts/tests inspect this exact source path rather than import `maistro_turing.runtime`
2. confirm package build does not explicitly include/reference the flat module
3. run Turing package tests after deletion
4. update reachability baseline if this file is tracked there

No deletion is performed in this audit checkpoint.
