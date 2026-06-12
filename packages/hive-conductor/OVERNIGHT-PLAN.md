# Overnight Session Plan: Make PM Fleet Actually Work

## The Goal
A 92-year-old PM who hates computers opens this app, types what they want in plain English, and the system does it. No forms. No dropdowns. No configuration. Just chat → action → results.

## What "works" means
1. PM types "what's happening with my sprint?" → system polls real Jira → returns a real summary
2. PM types "create an epic for the API migration" → system asks clarifying questions in chat → creates a draft → PM says "looks good" → it's done
3. PM types "who's blocked?" → system checks Jira → tells them who and why
4. PM types "do that every morning" → system saves it as a recurring action (the "button")
5. Every action that works once becomes a one-click repeat button in the sidebar

## The Stack (what's already real)
- LLM gateway: `LITELLM_PROXY_URL` → 54 models, working (tested: gemini-3.5-flash responds)
- Atlassian client: `maistro.tools.atlassian.AtlassianMCPClient` — full Jira/Confluence MCP client
- Credential store: `~/.conductor/user_credentials.enc` — encrypted PAT storage
- Chat endpoint: `POST /v1/chat/complete` — working, calls LLM with tool use loop
- PM runner: `maistro.agents.pm_runner` — has real Jira-driven execution code
- Frontend: React SPA on :8101, builds in <1s

## The Plan

### Phase A: Make chat the PM agent (not a generic chatbot)

**File: `backend/services/chat_completion.py`**

1. When a chat request comes in, inject the user's program context as system prompt:
   - Program name, goals, tools, constraints, stakeholders
   - "You are a PM agent for {program_name}. You manage {tools}. Your goals are {goals}."

2. Replace the Home Assistant tools with PM tools:
   - `poll_jira` — calls AtlassianMCPClient.jira_get_my_issues() with user's PAT from credential store
   - `search_jira` — calls jira_search_issues() with a JQL the LLM constructs
   - `get_issue` — calls jira_get_issue() for detail on one ticket
   - `search_confluence` — calls confluence_search()
   - `create_work_item` — creates a draft work item (not direct Jira write)
   - `check_blockers` — JQL for blocked/in-progress issues
   - `save_as_action` — persists the current tool call as a reusable button

3. Each tool actually executes (no stubs):
   - Pull PAT from credential store: `cred_svc.require_store().use_secret(user_id, "jira", lambda s: s)`
   - Call the real Atlassian MCP client
   - Return real data to the LLM for synthesis

4. After each successful tool execution, offer to save it:
   - LLM response includes a `_save_action` metadata field
   - Frontend renders a "Save as recurring action" button
   - Saved actions appear in the sidebar as one-click buttons

**Test after Phase A:**
```bash
curl -s -b cookies.txt http://localhost:8101/v1/chat/complete \
  -X POST -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"what issues are assigned to me in Jira?"}]}'
```
Expected: Real Jira issues in the response. Not a stub. Not "tool unavailable."

### Phase B: Make the frontend actually render

**Problem:** Page is blank (JS crash on load). 

1. Run `npx vite dev` (dev server with hot reload) and open in browser
2. Check console for the crash
3. Fix it
4. Verify: login → chat page renders → can type → gets real response

**Test after Phase B:**
- Open http://localhost:5173 (vite dev) or http://localhost:8101
- Type "hello" in chat
- Get a real response from gemini-3.5-flash
- Type "check my Jira"
- Get real Jira data back

### Phase C: Saved actions become buttons

**File: `backend/routes/chat.py` + new `backend/services/saved_actions.py`**

1. New model: `SavedAction(id, name, description, messages, schedule, created_at)`
2. New endpoints:
   - `POST /v1/actions` — save a chat exchange as a reusable action
   - `GET /v1/actions` — list saved actions
   - `POST /v1/actions/{id}/run` — re-execute a saved action
   - `DELETE /v1/actions/{id}` — remove
3. Frontend: sidebar shows saved actions as buttons
4. Clicking a button re-runs the saved messages through `/v1/chat/complete`

**Test after Phase C:**
- Chat: "poll my Jira" → get results
- Click "Save as action" → named "Daily Jira Poll"
- See "Daily Jira Poll" button in sidebar
- Click it → same results, no typing needed

### Phase D: Scheduling (the "do this every morning" part)

1. Saved actions can have a cron schedule
2. `POST /v1/actions/{id}/schedule` — set cron expression
3. Scheduler (already exists in `services/scheduler.py`) picks them up
4. Results go to a "Daily Report" or notification

### Phase E: Multi-team (the "14 teams" part)

1. Program context already supports multiple programs
2. Chat should be scoped to the active program (program picker in UI)
3. Each program has its own Jira project, goals, team
4. "Switch to Platform team" → context changes → tools scope to that team's Jira project

### Phase F: Power User Mode (if time permits)

Toggle in Settings or a keyboard shortcut (Cmd+Shift+P) that flips the UI into power mode:

**What it reveals:**
1. Every saved action shows its underlying DAG (the nodes, edges, models used)
2. Click any node → edit its prompt inline
3. Drag nodes to rearrange topology
4. See the optimizer's proposals overlaid on the DAG
5. Edit model per-node (the dropdown we already built)
6. See token counts, latency, cost per node from the last run
7. "Fork" an action to create a variant → A/B test via topology_compare

**Implementation:**
1. `useState<boolean>` in AppShell — `powerMode`
2. Persisted in localStorage
3. When on: saved actions expand to show DagBuilder inline
4. When off: just the button + last result
5. The existing DagBuilder, topology, optimizer pages become embedded views inside the action card

**The mental model:**
- Normal mode: "I click a button, magic happens"
- Power mode: "I can see and edit the magic"

Same data, same backend, just different UI depth.

## Build Loop Protocol

For each phase:
1. Write the code
2. Restart server: `kill $(lsof -ti :8101); sleep 1; [start command]`
3. **Test Layer 1 — API (curl/httpx):** hit the endpoint, assert real data comes back
4. **Test Layer 2 — Playwright:** headless browser loads the page, types in chat, asserts response renders
5. **Test Layer 3 — browser-use + Gemini Flash:** AI agent uses the app like a PM, reports what it sees
6. If any layer broken → read error logs (`tail /tmp/hive-conductor.log`) → fix → goto 2
7. All 3 layers pass → commit: `git add -A && git commit -m "phase X: description"`
8. Move to next phase

### Test Layer 1: API (after every code change)
```bash
# Chat works with real LLM
curl -s -b cookies.txt http://localhost:8101/v1/chat/complete \
  -X POST -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"what issues are assigned to me?"}]}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); c=d['choices'][0]['message']['content']; assert len(c)>50; assert 'stub' not in c.lower(); print('✅ API:', c[:100])"

# Saved actions persist
curl -s -b cookies.txt http://localhost:8101/v1/actions | python3 -c "import sys,json; print('✅ Actions:', len(json.load(sys.stdin)))"
```

### Test Layer 2: Playwright (after UI changes)
```typescript
// tests/e2e/pm-chat.spec.ts
test("PM can chat and get real Jira data", async ({ page }) => {
  await loginAsPM(page);
  await page.goto("/chat");
  const input = page.locator("input.input-field, textarea").first();
  await input.fill("what's on my plate in Jira?");
  await input.press("Enter");
  // Wait for real response (not instant = real LLM call)
  await page.waitForTimeout(10000);
  const response = page.locator(".message-content, [data-role='assistant']").last();
  const text = await response.textContent();
  expect(text.length).toBeGreaterThan(50);
  expect(text).not.toContain("stub");
  expect(text).not.toContain("unavailable");
});

test("PM can save an action as a button", async ({ page }) => {
  await loginAsPM(page);
  await page.goto("/chat");
  // ... run a command, then save it
  const saveBtn = page.locator("button", { hasText: /save|repeat/i });
  if (await saveBtn.isVisible()) {
    await saveBtn.click();
    // Verify it appears in sidebar/actions
    await page.goto("/");
    await expect(page.locator("text=Daily Jira Poll")).toBeVisible();
  }
});
```

### Test Layer 3: browser-use + Gemini Flash (end of each phase)
```python
# tests/e2e/test_pm_agent.py — updated per phase
async def test_chat_works():
    result = await browse(
        f"Go to {HIVE_URL}/chat. "
        f"Type 'what issues are assigned to me in Jira?' in the chat input and press Enter. "
        f"Wait for a response. "
        f"Does the response contain real Jira issue keys (like PROJ-123)? "
        f"Report 'REAL_DATA' if yes, 'STUB' if it says unavailable/stub, 'NO_RESPONSE' if nothing."
    )
    assert "REAL_DATA" in result

async def test_save_action():
    result = await browse(
        f"After getting a chat response, look for a 'Save' or 'Repeat' button. "
        f"Click it. Give it the name 'Morning Standup'. "
        f"Then check the sidebar — is 'Morning Standup' visible as a button? "
        f"Report 'SAVED' or 'NOT_FOUND'."
    )
    assert "SAVED" in result
```

### Validation Gate (must pass before moving to next phase)
All three layers must pass. If browser-use says "STUB" or "NO_RESPONSE", the phase is not done.

## Rules
1. **Don't stop until all phases are done and all success criteria pass.**
2. **If blocked on something (MCP unreachable, credential missing, API 400), skip it, work on the next phase, and come back.**
3. **No stubs. No placeholders. No faking. If it can't be real, leave a clear TODO and move on.**
4. **Commit after each working phase. Don't batch.**
5. **If the frontend is blank/broken, fix it first. Nothing else matters if the user can't see it.**
6. **Test all three layers. If one fails, fix before moving on. If truly blocked, note it and continue.**
7. **Use `--reload` on uvicorn so code changes auto-restart. Don't waste time on manual restarts.**
8. **Read error logs immediately on failure. Don't guess.**
9. **Our jobs depend on a flawless demo at 9 AM. This is not optional. It must work perfectly.**
10. **If all phases are done and tests pass, spend remaining time stress-testing:**
    - Rapid-fire 20 different chat prompts — every one must return real data
    - Refresh the page 10 times — never blank, never crash
    - Open in incognito — first-time experience must be seamless
    - Try to break it: empty messages, huge messages, special characters, rapid clicks
    - Simulate network lag: what happens if Jira is slow? Does the UI show loading state?
    - Run the full Playwright suite 3 times in a row — zero flakes
    - Run browser-use as a confused PM: "I don't know what to do" — does the app guide them?
    - Test the happy path end-to-end 5 times without touching the code between runs
11. **Leave a DEMO-READY.md with exact steps for the 9 AM demo: what to click, what to say, what the audience will see.**

## Server Start Command
```bash
cd packages/hive-conductor/backend
set -a; source ../../../.env; set +a
export LITELLM_API_BASE="${LITELLM_PROXY_URL}" LITELLM_API_KEY="${LITELLM_PROXY_KEY}" CHAT_DEFAULT_MODEL="gemini-3.5-flash"
export PYTHONPATH="$(pwd):$(pwd)/../../maistro-core/src"
uvicorn main:app --host 0.0.0.0 --port 8101 --reload
```
(--reload so code changes auto-restart)

## Success Criteria
- [ ] Type "what's on my plate?" → get real Jira issues
- [ ] Type "who's blocked?" → get real blocker analysis  
- [ ] Type "summarize the sprint" → get real LLM synthesis of Jira data
- [ ] Type "create an epic for X" → get a draft, confirm it, it saves
- [ ] Type "do that every morning" → action saved + scheduled
- [ ] Saved actions show as buttons in the UI
- [ ] Clicking a button re-executes without typing
- [ ] All of this works without the user knowing what Jira, LLM, or API means
- [ ] Power user toggle reveals DAGs, prompts, topology editor underneath

## Backlog (post-demo)

- [ ] **Responses API pattern** — Replace SSE streaming with stateless request/response model: POST creates a request ID, client polls or subscribes. Survives refresh, reconnect, and enables multi-device. Swaps stateful SSE for stateless architecture.
- [ ] **Jira project picker** — "Choose Jira projects" opens a fuzzy search against real Jira projects, user selects, auto-generates JQL
- [ ] **Confluence space scoping** — Default search to team's space, only search all of Confluence when explicitly asked
- [ ] **recharts dashboard** — PM-style donut charts, funnel stages, PM load visualization
- [ ] **Edit mode on agent buttons** — Click gear icon → inline edit prompt, JQL, schedule, name
- [ ] **Jira drafts refinement flow** — Chat creates pre-filled draft → guided interview to refine → template with actual Jira fields (required enforced, optional guided) → confirm posts to Jira. Source material already exists in a private working folder — includes `epic_template.md`, `jira_crafting.md`, `pm-knowledge-base-personas.md`, `base_context.md`, and the full `mcp-atlassian` client.
- [ ] **Research agent (smart)** — Reads blockers + program context + goals → proposes relevant web searches → user approves/modifies → deep research via browser-use → produces a daily report tailored to what you actually need (AI ecosystem changes, competitor moves, solutions to your specific blockers). Different every day based on current state.
- [ ] **CVE/Security agent** — Scans team's repos/deployments for CVEs, reports new vulnerabilities, suggests patches. Could pull from GitHub security advisories, NVD, or internal scanning tools. Shows "0 critical CVEs" prominently on dashboard when clean.

- [ ] **Hyperlight micro-VM sandbox** — Replace Docker containers for code-exec nodes with Hyperlight (https://github.com/hyperlight-dev/hyperlight). ~1ms startup, hardware isolation via KVM, host exposes only the functions the node needs (read_file, write_file, run_pytest, git_diff). No filesystem/network access by default. Perfect for mason/archie builder nodes that need to write code but must be sandboxed.

- [ ] **Microsoft Graph Engine for scale** — When DAGs hit thousands of nodes or thousands of concurrent users, replace in-memory Python dicts with Graph Engine (distributed RAM store, billion-node graphs, declarative message passing). The DAG executor becomes a thin layer on top of GE's computation engine. https://microsoft.github.io/GraphEngine/

- [ ] **Fluid Framework for collaborative DAG editing** — Multi-user real-time editing of DAG topologies, prompts, and configs. Multiple PMs see each other's changes live. Powers the "power user mode" collaborative view. https://fluidframework.com/
- [ ] **ONNX Runtime for local inference** — Run small models locally (eval scoring, guardrails, PII detection, intent classification) without API calls. Zero latency, zero cost for "light" nodes. Keeps sensitive data local. https://github.com/microsoft/onnxruntime
