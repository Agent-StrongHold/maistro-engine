# Code Quality Deep Dive — 2026-06-21

This report is a manual follow-up to the initial automated scan. It does **not** claim the whole repository has been equalized for quality. It examines representative high-signal `radon` and `vulture` findings, then reads the relevant code paths to separate tool noise from maintainability, testability, and correctness risks.

Security is intentionally out of scope for this report. When a file has security-adjacent naming, the analysis below treats it only as code-quality evidence: complexity, coupling, dead-code signal, testability, and assertion implications.

## Commands and scope

Commands run during this deep dive:

```bash
uv run python -m radon cc packages/hive-conductor/backend/services/chat_completion.py packages/hive-conductor/backend/routes/widgets.py packages/maistro-canvas/src/maistro_canvas/canvas/tool.py packages/maistro-core/src/maistro/skills/fixer.py packages/maistro-core/src/maistro/graph/optimizer.py packages/maistro-core/src/maistro/memory/scopes.py -s -n C
uv run python -m vulture packages/maistro-core/src/maistro/skills/fixer.py packages/maistro-core/src/maistro/memory/scopes.py packages/hive-conductor/backend/routes/widgets.py packages/maistro-canvas/src/maistro_canvas/canvas/tool.py --exclude '*/.venv/*'
```

The manual code tour focused on files where scanners found either high cyclomatic complexity or likely-dead symbols:

- `packages/hive-conductor/backend/routes/widgets.py`
- `packages/hive-conductor/backend/services/chat_completion.py`
- `packages/maistro-canvas/src/maistro_canvas/canvas/tool.py`
- `packages/maistro-core/src/maistro/skills/fixer.py`
- `packages/maistro-core/src/maistro/memory/scopes.py`
- `packages/maistro-core/src/maistro/graph/optimizer.py`

## Executive summary

| Priority | Finding | Evidence | Risk | Recommended next action |
|---|---|---|---|---|
| P0 | `execute_canvas` has a likely real bug in the `upload` action. | The upload branch creates `upload_img`, but stores and returns dimensions from `img`. | The action can raise at runtime or report the wrong dimensions, depending on previous branch state. | Fix immediately and add a unit test that uploads only `source_image` and asserts exact layer dimensions. |
| P1 | Widget routes are doing too much work in endpoint functions. | `widget_jira`, `widget_airtable`, and related Airtable endpoints mix credential resolution, query construction, HTTP calls, data shaping, aggregation, and broad exception handling. | Tests are likely to assert only response shape, missing broken query construction or display-mode behavior. | Extract route-independent helpers and add unit tests for query building, flattening, grouping, and error contracts. |
| P1 | Chat completion orchestration has high cognitive load and mixed responsibilities. | The non-streaming and streaming paths combine prompt construction, request assembly, tool loop control, tool execution, fallback behavior, tracing, and final response synthesis. | Edge cases around malformed tools, empty streamed content, and fallback retries are hard to cover soundly. | Split into a turn runner, tool-call executor, prompt-context builder, and streaming accumulator tests. |
| P2 | `fix_content` is a rule engine encoded as one long function. | Independent regex repair rules are applied sequentially in one high-complexity function. | Adding one rule can change another rule's behavior without focused tests. | Convert to ordered `RepairRule` objects with one parametrized test row per rule. |
| P2 | `matches_scope` is policy logic hidden in branch-heavy conditionals. | One function encodes all visibility rules for global/org/team/user/agent scopes. | Cross-tenant or fallback cases can regress without obvious test names. | Use per-scope predicates and a truth-table test matrix. |
| P3 | Vulture findings need an explicit reviewed allowlist. | FastAPI handlers are false positives, but unused parameters/helpers in canvas and utility modules need classification. | Dead-code scans will be ignored if true positives and framework false positives are not separated. | Add a `vulture` allowlist file and triage each high-confidence finding. |

## Detailed findings

### P0 — Canvas upload action has a likely runtime bug

`execute_canvas` is a single dispatcher for many actions (`generate`, `refine`, `reference`, `composite`, `text`, `upload`, and more). Its signature accepts a large set of optional parameters, most of which are meaningful only for some actions. That pattern raises branch-specific testing risk: one action can accidentally reference state initialized in another action.

The upload branch is the clearest concrete finding from the code tour. It decodes `source_image`, opens it as `upload_img`, re-encodes it, and then builds a layer using `img.width` and `img.height` rather than `upload_img.width` and `upload_img.height`. In an isolated `upload` call, `img` is not defined in that branch.

Why this matters for the quality rubric:

- **Assertion soundness:** a test that only asserts `result["action"] == "upload"` would miss wrong dimensions or a branch-local `NameError`.
- **Edge-case coverage:** the branch needs a test with no prior generated image and with a non-square image so width/height mixups are visible.
- **Cyclomatic complexity:** `radon` reports `execute_canvas` as `E (38)`, which matches the manual observation that it is an action router plus action implementations.
- **Maintainability:** optional parameters and branch-local state make it hard to know which inputs are valid for each action.

Recommended fix:

1. Replace `img.width`/`img.height` with `upload_img.width`/`upload_img.height` in the upload branch.
2. Add a unit test that passes a small base64 PNG through `execute_canvas(action="upload", source_image=...)` and asserts exact layer id presence, exact width, exact height, and persisted layer dimensions.
3. Split action handlers into functions such as `_execute_upload`, `_execute_text`, `_execute_composite`, each with a narrow parameter object.
4. Either remove the unused `reference_images` local or thread it into the action where it is intended to be used.

### P1 — Widget API endpoints mix transport, integration, transformation, and presentation

`widget_jira` has a large route body that performs user credential lookup, query defaulting, JQL operator cleanup, HTTP pagination, issue extraction, assignee aggregation, response formatting, and broad exception conversion. `widget_airtable` does the same style of work for Airtable: credentials and table config lookup, HTTP request execution, field flattening, optional grouping, optional display-field projection, table-mode response construction, and broad exception conversion.

The complexity here is not just line count. The functions contain several different logical contracts:

- Which credentials and defaults are selected for the user?
- How is user-provided query input converted into a safe backend query string?
- Which fields are flattened or displayed?
- What response shape is returned for `summary`, grouped, table, and display-field modes?
- What error envelope is returned for credential, config, HTTP, and parsing failures?

These are separable behaviors, but today they are embedded in route functions. That makes unit tests harder to write because the smallest testable unit is the whole endpoint plus external HTTP mocking. It also weakens assertions: tests are likely to assert that a response has an `items` key instead of proving that JQL construction, pagination, or grouping behaves correctly.

Scanner interpretation:

- `radon` reports `widget_airtable` as `E (38)`, `widget_jira` as `D (28)`, `widget_airtable_bases` as `C (20)`, and `widget_airtable_fields` as `C (14)`.
- `vulture` reports the route functions as unused, but those are likely FastAPI decorator false positives rather than dead endpoints.

Recommended refactor:

1. Extract pure helpers:
   - `build_jira_widget_query(query, jira_project) -> str`
   - `summarize_jira_issues(issues) -> WidgetSummary`
   - `flatten_airtable_record(record) -> dict[str, Any]`
   - `group_airtable_records(records, group_by) -> dict[str, list[dict[str, Any]]]`
2. Extract integration helpers:
   - `resolve_jira_credentials(user_id)`
   - `resolve_airtable_widget_config(user_id, app_id, table_id)`
   - `fetch_airtable_records(...)`
3. Keep FastAPI route functions thin: parse request, call helper/service, return typed response.
4. Add focused tests with exact assertions for JQL generation, grouped Airtable output, display-field projection, missing credentials, and upstream HTTP failure.
5. Add integration tests with mocked `httpx.AsyncClient` responses that exercise the route boundary and verify the public response shape.

### P1 — Chat completion turn handling and streaming are tightly coupled

The chat completion service has several hotspot functions:

- `_get_airtable_creds` layers environment, store, and config fallback behavior in one function while swallowing some exceptions.
- `_build_system_prompt` composes a large prompt with profile cache, Airtable/Jira context, and optional guidance sections.
- `_run_chat_completion_inner` owns the tool loop, LLM request creation, tool-call parsing, tool execution, message mutation, final synthesis, tracing, and error fallback.
- `run_chat_completion_streaming` repeats much of the turn orchestration while also managing SSE status events, streamed token accumulation, structured tool-call accumulation, non-streaming fallbacks, textual tool-call leak detection, tracing, and result events.

This is a test-design problem as much as a code-structure problem. The current shape encourages broad tests like "chat completion returns something". Those tests do not strongly measure the intended contracts around malformed tool arguments, tool exceptions, exhausted tool iterations, fallback when streaming yields no content, or model output that leaks tool calls as text.

Scanner interpretation:

- `radon` reports `run_chat_completion_streaming` as `D (29)`.
- It also reports several related helpers as `C`: `_tool_suggest_widgets`, `_get_airtable_creds`, `_run_chat_completion_inner`, `_tool_favorite_model`, `_build_system_prompt`, `_tool_search_jira`, `_tool_suggest_workflows`, and `_tool_get_issue`.

Recommended refactor:

1. Introduce a `ChatTurnRunner` that owns the bounded tool loop and returns a typed result such as `ChatTurnResult(content, tool_calls, tool_results, exhausted)`.
2. Introduce a `ToolExecutor` that normalizes JSON decoding, unknown tool names, tool exceptions, and result summarization.
3. Introduce a `PromptContextBuilder` that returns structured prompt sections before rendering text.
4. Keep streaming as an adapter: convert turn events into SSE events, not a second orchestration implementation.
5. Add unit tests for each edge case:
   - malformed tool-call JSON becomes `{}` or a typed error according to contract;
   - unknown tool name yields a deterministic tool-result payload;
   - five tool iterations without final content returns a documented exhausted-loop response;
   - streaming with no chunks falls back exactly once;
   - textual tool-call leak detection retries and records a warning path.

### P2 — `fix_content` should become a rule pipeline

`fix_content` applies many independent transformations: unicode normalization, direction-marker removal, dynamic execution replacement, suspicious import replacement, credential placeholdering, prompt-injection wording replacement, command replacement, trust-boundary wording replacement, and other string repairs. The current function is understandable in small pieces, but the full sequence has high cyclomatic complexity and hidden coupling between rules.

The quality issue is not that the rules exist. The issue is that rule ordering and rule intent are not first-class. If a new repair is inserted in the middle, it can change the input to downstream regexes. Without rule-level tests, assertion soundness depends on broad before/after examples that may not identify which rule failed.

Scanner interpretation:

- `radon` reports `fix_content` as `D (25)`.
- `vulture` reports `fix_content` and `is_deeply_flawed` as unused in the targeted scan. That may be a real dead-code signal or a dynamic/public API false positive; it needs classification.

Recommended refactor:

1. Define a small `RepairRule` data structure with `name`, `pattern`, `replacement` or `apply`, and optional `reason`.
2. Store ordered rules in a module-level tuple.
3. Implement `fix_content` as a loop over rules.
4. Add one parametrized test row per rule with exact expected output.
5. Add one ordering test where two rules could interact.
6. If the functions are public API, add them to a vulture allowlist with a reason; otherwise remove them.

### P2 — `matches_scope` is compact but encodes critical policy branches

`matches_scope` is short enough to read, but its branch count is high because it implements a visibility policy across `global`, `org`, `team`, `user`, and `agent` scopes. The risk is not raw length. The risk is that each branch encodes a cross-context data-visibility rule, and those rules need a truth table.

Recommended refactor and test plan:

1. Extract named predicates such as `_matches_global`, `_matches_org`, `_matches_team`, `_matches_user`, and `_matches_agent`, or use a mapping of scope kind to predicate.
2. Add parametrized tests where each row includes:
   - stored entry scope;
   - querying scope;
   - expected boolean;
   - explanation of why it should match or not match.
3. Cover at least these cases exactly:
   - global entry visible to any query scope;
   - org entry visible only inside the same org;
   - team entry not visible to another team in the same org;
   - user entry not visible to another user in the same org/team;
   - agent entry visible only to the same agent;
   - unknown scope never matches.

Scanner interpretation:

- `radon` reports `matches_scope` as `C (20)`.
- `vulture` reports `build_scope_filter` and `matches_scope` as unused in the targeted scan. This should be triaged as either public utility surface or dead code.

### P3 — Graph optimizer prompt proposal is complex but more cohesive than other hotspots

`GraphOptimizer._propose_prompt` was flagged by `radon` as `D (21)`. Manual inspection shows that most of the complexity comes from assembling a meta-prompt with pipeline topology, current prompt, performance signal, failure patterns, upstream/downstream context, and rewrite instructions.

This is a lower-priority finding because the function is cohesive: it exists to build one LLM prompt and call the configured model. Still, it would benefit from smaller rendering helpers because prompt regressions are hard to detect with only end-to-end optimizer tests.

Recommended improvements:

1. Extract pure helpers for `render_performance_signal`, `render_failure_patterns`, and `render_node_context`.
2. Add snapshot-style tests for prompt rendering using stable fake `GraphConfig` and `OptimizationSignal` data.
3. Assert exact inclusion of objective, current prompt, success rate, bottleneck rank, observed failures, upstream node, downstream node, and return-format instruction.
4. Keep the LLM call mocked in unit tests and reserve integration tests for provider adapters.

### P3 — Vulture needs a reviewed baseline, not blanket failure or blanket ignore

The vulture run surfaced three categories of findings:

1. **Framework false positives:** FastAPI route functions registered through decorators look unused to static analysis.
2. **Likely true positives:** local variables such as `reference_images` that are assigned but not used.
3. **Unclassified public/dynamic APIs:** helpers such as `execute_canvas`, `destroy_canvas`, `save_character_reference`, `load_character_reference`, `build_scope_filter`, and `fix_content` may be invoked dynamically or may be stale.

The current scanner posture should remain advisory until this is triaged. Making vulture fail CI before classification would create noise. Ignoring it completely would miss true dead-code and unused-variable defects.

Recommended baseline process:

1. Create a `vulture_allowlist.py` or equivalent file with one line per accepted false positive and a short reason.
2. Fix high-confidence true positives immediately, starting with unused locals and branch-local bugs.
3. For public APIs, add either direct tests/imports or allowlist entries documenting the dynamic call path.
4. Re-run vulture and ratchet the allowlist down over time.

## Expanded borderline-case investigation and improvement options

The follow-up investigation looked for cases that are not obviously good or bad from scanner output alone. Each negative finding below includes 3-5 concrete improvement options so follow-up PRs can choose the smallest safe slice instead of attempting another broad rewrite.

### Finding A — Canvas dispatcher and reference helpers

Borderline classification:

- `execute_canvas` being reported unused by vulture is ambiguous because canvas tools may be invoked dynamically by a tool registry or agent runtime. Treat it as **unclassified public/dynamic API** until the call path is documented or tested.
- `destroy_canvas` is also ambiguous: it is a plausible lifecycle API, but no direct static caller appeared in the targeted vulture scan.
- `reference_images` is a stronger true-positive signal because it is a local parameter accepted by `execute_canvas` but not used by any inspected branch.
- `created_at` and `CREATE_TABLE_SQL` are borderline: the dataclass field and SQL string document intended persistence shape, but the SQL constant is not executed in this module and may belong in a migration or registry module.
- The upload branch is not borderline; it is a likely bug because it uses `img` where the branch-local image is named `upload_img`.

Potential improvements:

1. Fix the upload branch dimension bug and add a regression test with a non-square image.
2. Split `execute_canvas` into action-specific helpers while preserving the existing public function as a thin dispatcher.
3. Replace action-specific optional parameters with typed request dataclasses or Pydantic models so invalid parameter combinations are rejected early.
4. Decide whether `reference_images` is part of the intended public contract; either implement it in the relevant action or remove it from the signature.
5. Move `CREATE_TABLE_SQL` into a migration/schema module or add an explicit initialization function and tests that prove it is used.

### Finding B — Widget endpoints and dashboard helper routes

Borderline classification:

- FastAPI-decorated functions reported as unused are likely vulture false positives, not dead endpoints.
- The repeated credential lookup loops are not technically incorrect, but they create hidden coupling and make failure behavior inconsistent between Airtable routes.
- `capture_screenshot` is a valid endpoint shape, but its timer-based waits and local URL assumption make it an e2e-style helper embedded in the API layer.
- Broad `except Exception` blocks are borderline in dashboard widgets because widgets may prefer graceful degradation, but returning truncated strings makes exact integration assertions and operational triage harder.

Potential improvements:

1. Add a vulture allowlist entry for FastAPI route functions with a comment that decorators register them.
2. Extract shared Airtable credential resolution and table/base metadata fetching into service helpers used by every Airtable widget route.
3. Extract pure transformation helpers for JQL cleanup, issue aggregation, Airtable field flattening, grouping, and display-field projection.
4. Replace ad-hoc error dictionaries with typed response models that distinguish missing credentials, upstream HTTP errors, and empty data.
5. Move screenshot capture to a dedicated service with injectable browser/page dependencies and deterministic timeout settings for e2e tests.

### Finding C — Chat completion orchestration

Borderline classification:

- A state-machine-like streaming function can justifiably have more branches than ordinary business logic, but the current streaming path also duplicates non-streaming orchestration decisions.
- Fallback to non-streaming completion is a useful resilience path, but the branch is hard to assert because it is embedded in the generator.
- Swallowing malformed tool-call JSON into `{}` may be acceptable as compatibility behavior, but it needs an explicit contract and tests.
- Textual tool-call leak detection is useful but brittle because it scans model text for tool names rather than using a typed parser or finish reason.

Potential improvements:

1. Create a single bounded `ChatTurnRunner` used by both streaming and non-streaming paths.
2. Extract tool-call normalization into a pure helper that returns either parsed arguments or a typed parse-error object.
3. Convert streaming into an adapter over typed turn events so SSE formatting is testable without a real LLM stream.
4. Add fake-LLM tests for empty stream fallback, malformed JSON, tool exception, unknown tool, and exhausted tool-loop cases.
5. Replace silent broad streaming fallback with logged, countable fallback outcomes that tests can assert through emitted events or result metadata.

### Finding D — `fix_content` rule sequence

Borderline classification:

- A long repair function is understandable when read top-to-bottom, but it is still fragile because ordering is implicit.
- Some regex replacements are independent, while others can alter text that later rules inspect. This makes regression tests more important than raw complexity reduction.
- Vulture reporting `fix_content` and `is_deeply_flawed` as unused may be a real dead-code signal or a public utility false positive; the module needs an explicit owner/call-path decision.

Potential improvements:

1. Convert each repair into a named rule with a reason, pattern, and replacement/apply function.
2. Add one exact-output parametrized test per rule and one ordering test for interacting rules.
3. Preserve a single `fix_content` public API as an orchestrator over the rule list.
4. Add docstrings or comments for rules whose replacement is intentionally conservative.
5. If no runtime caller exists, either remove the module or keep it behind an explicit public API test and vulture allowlist entry.

### Finding E — Memory scope matching

Borderline classification:

- `matches_scope` is compact and has useful inline comments, so it is not a readability failure in isolation.
- It is still a negative quality finding because branch-heavy policy logic should be backed by a truth table, not just implementation comments.
- Vulture's unused finding may be false if scope helpers are intended library surface, but a lack of static callers means tests must prove they are still part of supported behavior.

Potential improvements:

1. Add a parametrized truth-table test for global, org, team, user, agent, cross-org, cross-team, and unknown-scope cases.
2. Extract per-scope predicate helpers only after the truth table exists, so the refactor can be behavior-preserving.
3. Make org/team/user/agent matching expectations explicit in test names.
4. Add a public API import test or vulture allowlist entry if the helpers are intentionally exported.
5. Consider returning an enum/reason in an internal helper for easier diagnostics in failed tests.

### Finding F — Graph optimizer prompt rendering

Borderline classification:

- `_propose_prompt` is more cohesive than the other complexity hotspots because it mainly renders a prompt and calls the LLM.
- The risk is snapshot drift: prompt text can lose critical sections without causing type or lint failures.
- Complexity here is acceptable as a temporary condition if prompt-rendering coverage is exact and stable.

Potential improvements:

1. Extract deterministic render helpers for node context, performance signal, failure examples, and rewrite instructions.
2. Add snapshot or exact-substring tests for each required prompt section.
3. Test rank suffixes and missing `node_metric` fallback behavior with stable fake signals.
4. Keep the LLM call mocked in unit tests and verify only the rendered messages and returned stripped text.
5. Document which prompt sections are contractual versus advisory so future prompt edits know what must remain stable.

### Finding G — Vulture baseline quality

Borderline classification:

- Treating every vulture finding as a failure would currently be too noisy because decorators and dynamic tool entry points create false positives.
- Treating every vulture finding as advisory forever would also be a quality failure because it hides true positives like unused locals and unexercised helpers.

Potential improvements:

1. Add `vulture_allowlist.py` with reviewed false positives and a one-line reason per symbol.
2. Separate findings into `framework false positive`, `dynamic public API`, `test gap`, and `remove/fix` buckets in the scan report.
3. Make high-confidence local unused variables blocking once the current baseline is cleaned up.
4. Add tests or explicit imports for dynamic public APIs that should remain supported.
5. Ratchet the allowlist by failing CI only on new unclassified findings.

## Remediation specs

Each negative finding now has an owning spec so follow-up work can land in focused, reviewable slices:

- Canvas dispatcher/upload/reference ownership: [SPEC-259](specs/SPEC-259-canvas-tool-action-contracts.md)
- Shared widget/chat tool-call protocol and Airtable cache: [SPEC-260](specs/SPEC-260-shared-tool-call-cache.md)
- Skill fixer rule pipeline: [SPEC-261](specs/SPEC-261-skill-fixer-rule-pipeline.md)
- Memory scope truth table: [SPEC-262](specs/SPEC-262-memory-scope-policy-truth-table.md)
- Graph optimizer prompt rendering contracts: [SPEC-263](specs/SPEC-263-graph-optimizer-prompt-rendering-contracts.md)
- Vulture/radon scanner baselines: [SPEC-264](specs/SPEC-264-quality-scanner-baselines.md)

## Scope caveat: these specs are a triage map, not a proof of perfection

Completing SPEC-259 through SPEC-264 would close the negative findings identified in this manual deep dive, but it would not prove the implemented code is globally optimal or "perfect." The report is a representative, high-signal investigation over the files surfaced by radon/vulture and manual review on 2026-06-21. It does not exhaustively prove every package, every runtime path, every integration, or every future regression.

After SPEC-264 is complete, the expected state is:

- the current findings have owners, tests, and scanner baselines;
- new vulture/radon regressions are easier to detect;
- follow-up PRs have narrower acceptance criteria; and
- reviewers can distinguish fixed findings from accepted/dynamic/API-surface exceptions.

It should still be followed by ongoing scanner ratchets, mutation testing on extracted helpers, integration/e2e coverage for real user paths, and new deep dives whenever scanners or incidents reveal fresh hotspots.

## Test-quality implications

The deeper code tour suggests several specific places where tests should become stronger:

- Prefer exact output assertions over existence checks for widget response modes, canvas layer dimensions, prompt-rendered sections, and scope-policy truth tables.
- Use unit tests for pure transformations: JQL construction, Airtable flattening/grouping, prompt rendering, repair rules, and scope predicates.
- Use integration tests for route boundaries and LLM/tool orchestration with fake adapters.
- Add e2e tests only where user-visible behavior crosses multiple subsystems, such as a chat request that triggers a tool call and returns a final assistant response.
- Mutation testing should start on small extracted pure helpers before attempting large async orchestration functions.

## Recommended remediation order

1. Fix the `execute_canvas` upload dimension bug and add an exact regression test.
2. Extract and test pure widget helpers for Jira query construction and Airtable record shaping.
3. Add a vulture allowlist and classify every current finding as false positive, public dynamic API, or dead code.
4. Split chat completion turn orchestration from SSE streaming and add edge-case unit tests around tool-call handling.
5. Convert `fix_content` to a named rule pipeline with parametrized tests.
6. Convert `matches_scope` tests into a visibility truth table.
7. Extract graph optimizer prompt-rendering helpers and snapshot their deterministic output.

## Bottom line

The deeper review found real code-quality issues behind the scanner output. Some vulture findings are framework noise, but at least one canvas finding appears to be a concrete runtime bug. The highest leverage next step is not to add more scanners; it is to convert the scanner findings into smaller units with exact assertions, then ratchet advisory scanner output into reviewed baselines.
