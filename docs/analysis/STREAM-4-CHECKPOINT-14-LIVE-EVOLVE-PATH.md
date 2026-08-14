# Stream 4 Checkpoint 14: Live Evolve Product Path

Date: 2026-08-14
Source audited: `develop`

This checkpoint traces the mounted Hive Evolution API and background service to the actual `maistro-evolve` domain loop. It confirms that `Evolve timer -> Schedule -> Run` is a real production convergence task, not merely conceptual cleanup.

## 1. Hive Evolution is live and process-started

Hive application lifespan starts `services.evolution.start_evolution()` and later stops it during shutdown.

Mounted `/v1/evolution` routes expose:

- status
- population
- genome detail
- champion
- lineage
- tournament leaderboard/battles/stats
- seed population
- manual cycle trigger

Classification: `live Evolve product/service surface`.

## 2. EvolutionService owns a private process-lifetime scheduler

`start_evolution()`:

- constructs a process-global `_EvolutionService`
- creates an asyncio task for `run_loop()`

`run_loop()`:

- creates PopulationStore and EloTournament
- sleeps 300 seconds
- calls `_run_one_cycle()`
- records last-cycle errors
- repeats while `_running`

This timer is independent of the existing Hive Schedule API and independent of canonical Run.

Classification: `live private scheduler/lifecycle`.

## 3. Manual cycle route bypasses Schedule/Run as well

`POST /v1/evolution/cycle` calls the private service method `_run_one_cycle()` directly and returns `status=completed` + cycle count.

Therefore both automatic and operator-triggered Evolve cycles bypass canonical Schedule/Run/Attempt/Event.

### Stream 1 / Stream 7 target

Automatic:

`Schedule -> canonical Run -> Evolve graph/domain cycle`

Manual:

`explicit Run request -> same canonical Evolve execution path`

Do not preserve separate timer and manual execution implementations.

## 4. Live EvolutionService owns product/service state that is not universal Run state

The service tracks:

- population
- tournament
- cycle count
- last cycle error
- process running flag

Population/tournament/cycle lineage are Evolve domain state and should remain specialized.

The process task/running/error lifecycle should not become another universal execution source after convergence.

## 5. EvolutionService also owns direct LLM provider invocation

`_build_llm_call()` resolves MAIstro/LiteLLM base URL and keys, builds an HTTP chat-completion callable, and passes it directly into EvolutionCycle.

This bypasses canonical Binding/Provider/Invocation/Attempt.

### Stream 6 handoff

Preserve Evolve's need to evaluate/self-improve with selectable models, but route managed platform calls through canonical Provider/Invocation so usage, credentials, fallback, and provenance are authoritative.

## 6. EvolutionCycle contains substantial Evolve domain behavior worth preserving

`maistro_evolve.cycle.EvolutionCycle` owns specialized evolutionary semantics including:

- hard non-overridable per-cycle resource ceilings
- evaluation batches
- EMA folding of noisy benchmark scores
- tournament battles / Elo
- fitness computation
- island populations / migration
- breeding and mutation
- self-improvement of top genomes
- typed-fixer hyper-mutation
- reflection/propose-verify behavior
- model-roster constraints
- benchmark-specific learning history

These are not generic Run lifecycle responsibilities.

Classification: `preserve Evolve domain cycle`.

## 7. Hard resource caps are migration requirements

EvolutionConfig enforces hard upper bounds for:

- eval batch size
- population size
- tournament size
- self-improve top-N
- self-improve candidate count
- history window
- island count
- migration interval

These are safety/cost invariants around Evolve execution and should remain enforced after cycles become canonical Runs.

Do not accidentally turn migration to Schedule/Run into removal of Evolve's domain-specific compute ceilings.

## 8. Current process timer has no persisted schedule/run history

EvolutionService keeps cycle count and last error in process state. Restart reconstructs the service and timer but does not make the process-lifetime timer itself a durable Schedule/Run history.

PopulationStore may persist its own domain data, but that is distinct from authoritative execution provenance.

Canonical Schedule + Run can improve observability/recovery without moving population/tournament state into Run.

## 9. Evolution route mutates domain state directly

`POST /seed` imports `emergency_spawn` and inserts spawned genomes directly into the population.

That is appropriate as an Evolve domain operation, but authorization/audit/resource scoping should eventually be shared with canonical product resource services rather than depending solely on route-level global permission.

## Updated Stream 7 parity priority

### Live behavior that must survive

- background evolution cadence
- manual cycle
- population/champion/lineage/tournament UX
- seed population
- EvolutionCycle evolutionary semantics and hard caps

### Universal mechanics to replace

- process-lifetime timer
- private asyncio task lifecycle
- direct LLM transport/credential use
- cycle execution outside canonical Run/Event

### Unreachable/offline behavior that is not current product parity

Other `maistro-evolve` provider/terminal-runner modules identified by the reachability ratchet should be migrated only where they feed the live product or remain intentionally supported developer tools.

## Immediate handoffs

### Stream 1

Canonical Schedule/Run should own automatic and manual Evolve execution provenance.

### Stream 2

Cycle start/completion/failure and population mutation signals should project through canonical Event where useful; Evolve domain data remains specialized.

### Stream 6

Replace direct `_build_llm_call` platform invocation with canonical provider/binding/invocation mechanics while retaining model-roster and evaluation semantics.

### Stream 7

This is a live migration path. `Evolve timer -> Schedule -> Run` should be prioritized ahead of unreachable auxiliary Evolve modules.

## Reachability lesson

A package can contain a mix of live domain core and unreachable auxiliary execution surfaces. Migration priority should follow the mounted/product caller graph, not package-level labels.
