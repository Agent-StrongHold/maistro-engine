# Durable Attempt Runtime Boundary

This slice moves durable Graph physical execution toward the canonical boundary:

`Run -> NodeRun -> Attempt -> ExecutionRuntime`

The durable Graph checkpoint remains the single persistence envelope for the canonical `Run`, chronological `NodeRun`s, Graph-specific traversal state, and now physical `Attempt`s. The design deliberately avoids dual-writing a separate Run store.

`AttemptExecutionService` remains the physical execution service. It may defer logical reconciliation when a domain executor such as Graph owns the final NodeRun outcome semantics. Deferring logical reconciliation does not bypass Attempt persistence, runtime execution identity, cancellation, deadline, or terminal Attempt recording.

The next commit in this slice wires the concurrent durable frontier executor through the durable execution-store adapter and `AttemptExecutionService`, then reloads the optimistic durable record before Graph result folding so persisted Attempts cannot be overwritten by a stale checkpoint.
