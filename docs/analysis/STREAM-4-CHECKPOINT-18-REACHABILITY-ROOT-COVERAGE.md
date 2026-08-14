# Stream 4 Checkpoint 18: Reachability Root Coverage

Date: 2026-08-14
Source audited: `develop`

This checkpoint audits the reachability ratchet itself after the Turing/Bootstrap/Registry package classification.

## Finding: Turing standalone backend is outside the scanner graph

`scripts/check-reachability.py` collects production modules from:

1. every `packages/*/src` package tree
2. the flat `packages/hive-conductor/backend` tree

It does **not** collect `packages/maistro-turing/backend`.

The scanner roots Turing only through the dynamic root:

`maistro_turing.runtime`

Therefore the current baseline entries such as:

- `maistro_turing.memory`
- `maistro_turing.producers`
- `maistro_turing.providers`
- `maistro_turing.schema`
- `maistro_turing.tools`

mean "not reachable from the library/runtime roots currently modeled by the scanner." They do not prove those modules are unreachable from the standalone Turing FastAPI backend, because that backend and its flat route/config/state modules are absent from the collected graph.

## Why this matters

Stream 4's operating rule is that reachability is a floor, not proof. This scanner blind spot is the inverse problem: a real product entry point can exist outside the scanner's modeled roots, making baseline classifications incomplete for that product.

Do not use Turing baseline entries alone as deletion evidence until standalone-backend reachability is traced manually or the scanner is extended safely.

## Bootstrap and Registry comparison

The scanner does explicitly model:

- `maistro_bootstrap` as a static root
- `maistro_registry.cli` as a static root

Registry is additionally confirmed live through `.github/workflows/registry.yml`.

Bootstrap has a real Hive control-plane caller in `routes/install.py`, but because Hive is already rooted and `maistro_bootstrap` is also a root, it is covered from both directions sufficiently for the current audit purpose.

## Safe follow-up

Do **not** simply add `packages/maistro-turing/backend` as another unprefixed flat tree. Its module names (`main`, `config`, `routes`, etc.) collide with Hive's flat backend names in the scanner's global module namespace.

A safe scanner enhancement needs an explicit namespace/model for multiple flat application roots, for example:

- collect each flat backend under a synthetic scanner namespace while preserving its local-import resolution semantics, or
- teach the scanner about multiple independent flat import roots and traverse each graph separately before unioning reachable package modules.

That is tooling work, not a canonical domain change, but it should be implemented deliberately with regression tests before relying on the ratchet for Turing deletion decisions.

## Classification impact

- Turing package-level structural-unreachability findings remain useful leads, not deletion verdicts.
- The explicit shadowed `maistro_turing/runtime.py` dead-file finding remains independently strong because it is based on Python import resolution and the file's own documented replacement, not the ratchet.
- Bootstrap and Registry classifications remain unchanged.
