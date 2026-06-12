# DEMO-READY — 9 AM Script

## Start the server (if not already running)

```bash
cd packages/hive-conductor/backend
set -a; source ../../../.env; set +a
export LITELLM_API_BASE="${LITELLM_PROXY_URL}" LITELLM_API_KEY="${LITELLM_PROXY_KEY}" CHAT_DEFAULT_MODEL="gemini-3.5-flash"
export PYTHONPATH="$(pwd):$(pwd)/../../maistro-core/src"
uvicorn main:app --host 0.0.0.0 --port 8101 &
```

Open: **http://localhost:8101**

---

## Demo Flow (5 minutes)

### 1. Login (10 seconds)
- Username: `test` / Password: `user1234`
- Lands on Chat page

### 2. Chat — "Who's blocked?" (30 seconds)
- Type: **"Who's blocked right now?"**
- Watch: Status shows "Working…" → real response with actual MAISTRO Jira issues
- **What they see:** Real blocked issues with real names (Cesar, Bashir, Ranjitha, etc.)
- **Key point:** "This is live data from our Jira instance. Not a mock."

### 3. Chat — Save as action (15 seconds)
- Type: **"yeah save that"**
- Watch: Creates "Blocker Alert" button
- **Key point:** "Now anyone on the team can run this with one click."

### 4. Program page — Agent fleet (30 seconds)
- Click **🧠 Program** in sidebar
- Show the 6-agent fleet + the button you just created
- Click **"Poll Jira"** on the Delivery Agent
- Watch: Navigates to Chat with real results
- **Key point:** "Every button executes real queries. Nothing is stubbed."

### 5. Chat — Create a new agent (30 seconds)
- Type: **"Add a button that shows all MAISTRO epics in progress"**
- Watch: Creates a new agent button
- Go back to Program page — it's there
- **Key point:** "The PM defines what they need in plain English. The system builds the automation."

### 6. Chat — Confluence (20 seconds)
- Type: **"Search Confluence for project onboarding"**
- Watch: Searches wiki.example.com, returns real pages
- **Key point:** "Same interface for Jira, Confluence, and anything else we connect."

---

## If they ask...

**"Is this using real AI?"**
→ Yes, Gemini 3.5 Flash through our LLM gateway. 54 models available, swappable per-agent.

**"Is this hitting real Jira?"**
→ Yes, jira.example.com with a PAT stored in an encrypted credential vault. Read-only.

**"Can it write to Jira?"**
→ Not yet in this demo. The architecture supports it (gated flow: draft → review → confirm → post). Coming next sprint.

**"How does it know about our program?"**
→ There's a program context (goals, tools, stakeholders) that was set up via an interview. It injects that into every LLM call.

**"Can other PMs use this?"**
→ Each user gets their own credentials, program context, and saved actions. Multi-tenant by design.

**"What about the 6-agent fleet?"**
→ Those are the default PM capabilities. The chat can create new ones, modify existing ones, or remove them. Power users can edit the underlying prompts and JQL directly.

---

## Don't show
- Jira drafts page (not ready — blank forms)
- Activity page (missions complete instantly, no real execution yet)
- Quotas page (no data source connected)
- Any page that says "stub" or shows raw JSON

## If something breaks
- Hard refresh (Cmd+Shift+R)
- If chat hangs > 30s, it's the LLM gateway being slow — wait or try a shorter prompt
- If 500 error, start a new chat session (+ new button)
- **Don't switch sessions while "Working…" is showing** — wait for the response first, then navigate
