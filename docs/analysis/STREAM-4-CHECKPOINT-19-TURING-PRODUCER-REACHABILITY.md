# Stream 4 Checkpoint 19: Turing Producer Reachability

Date: 2026-08-14
Source audited: `develop`

This checkpoint manually traces Turing's proactive-producer claim because the repository reachability scanner does not model the standalone Turing backend.

## Advertised behavior

`packages/maistro-turing/README.md` describes the package as adding mood, personality, drives, and "proactive producers that act on them without being prompted."

The active producer implementation in `maistro_turing.producers` contains:

- `BlogProducer`
- `SelfReflectionProducer`
- `CuriosityProducer`
- `EmotionalProducer`
- drive calculation from self-model facet scores + mood
- model calls through `TuringProviderBridge`
- self-write security scanning through `TuringSecurityBridge`
- episodic-memory writes through `TuringMemoryBridge`

That domain behavior is real and worth preserving.

## Standalone backend trace

The standalone backend mounts:

- state
- feed
- chat
- admin
- auth
- health

`TuringState` constructs:

- `TuringMemoryBridge`
- `TuringSecurityBridge`
- `TuringProviderBridge`
- `TuringClassifierBridge`
- `TuringActor`

It does **not** construct any producer class or register a producer cadence/trigger.

The feed route supports receiving artifacts over POST from a Turing-internal service principal and listing them for the frontend. That proves an ingestion surface exists, but it does not prove the producers themselves are scheduled or executed by this backend.

`maistro_turing.__init__` exports `FakeReactor`, `IntervalTrigger`, and the bridge/self-model APIs, but not producer constructors. `cognition/reactor.py` describes `FakeReactor` as a research-branch test fixture mirroring a real reactor contract; there is no real producer scheduler in that cognition package.

Repository code search also found no production construction site for `BlogProducer` by symbol name. Search-index absence is supporting evidence only, not the primary proof.

## Classification

Current Turing proactive production is **implemented domain behavior without a verified live execution owner**.

Preserve:

- drive computation
- producer prompts/domain semantics
- self-model/mood eligibility
- producer output kinds
- security scan requirement
- memory capture behavior

Do not preserve as a new private scheduler/lifecycle.

Target migration:

`Schedule -> Run -> Turing producer Graph/Node -> Binding/Invocation -> Artifact/Event`

or an equivalent canonical scheduled child-Run model once Streams 1/2/5/6 contracts are available.

The Turing feed remains a product projection/ingestion surface during migration.

## Additional dead shadow file

`packages/maistro-turing/src/maistro_turing/producers.py` explicitly declares itself dead code for the same reason as the flat `runtime.py`: sibling `producers/` wins Python import resolution and contains the copied active implementation.

Delete-after prerequisites are the same class as `runtime.py`:

1. confirm no exact-path external tooling depends on the inert source file
2. delete on a cleanup branch, not the audit branch
3. run the documented Turing package test command
4. run lint/type-check/package build
5. update reachability/docs as appropriate

## Documentation implication

Until a producer execution owner is verified or wired, documentation should distinguish:

- producer implementations exist
- feed ingestion exists
- autonomous producer scheduling/execution is not currently verified on a product path

This avoids repeating the repository's prior pattern of describing implemented source as active runtime behavior.
