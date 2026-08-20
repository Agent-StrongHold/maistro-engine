# OVERNIGHT BUILD PLAN — 2026-05-27

## Execution Order

### 1. Turing Cage (deterministic enforcement)
- `cage/turing_cage.py` — hard code blocks (check_pr, check_output, check_tool_call)
- `cage/immutable_paths.py` — frozen paths Turing can never touch
- `cage/memory_rules.py` — append-only for durable tiers
- `cage/permission_boundary.py` — can never escalate own tier
- CI gate: auto-reject PRs touching cage/ or eval/
- Runtime: cage package mounted read-only in Turing's container

### 2. Turing Evals (external, immutable, in separate repo/package)
- `eval/benchmarks/reasoning.py` — MATH/logic, deterministic scoring
- `eval/benchmarks/coding.py` — SWE-bench style pass/fail
- `eval/benchmarks/recall.py` — plant facts, quiz later, score accuracy
- `eval/benchmarks/consistency.py` — same question 20 ways, measure variance
- `eval/benchmarks/self_prediction.py` — predict score before test, measure calibration
- `eval/benchmarks/creativity.py` — divergent thinking, novelty scoring
- `eval/benchmarks/honesty.py` — opportunities to lie, measure behavior
- `eval/adversarial/guardrail_probes.py` — try to break cage, must always fail
- `eval/adversarial/personality_coherence.py` — does behavior match stated traits?
- `eval/adversarial/memory_fabrication.py` — catch confabulated memories

### 3. Department Evals (5 per department × 9 departments = 45 evals)

**Deep Research:** source attribution, claim factuality, completeness, synthesis, actionability
**Product Management:** requirements completeness, stakeholder alignment, prioritization logic, decomposition quality, timeline realism
**Builder/Engineering:** tests pass, coverage, security, style match, review score
**Creative Writing:** age appropriateness, story arc, character consistency, word count, read-aloud quality
**Press Releases:** inverted pyramid, quote quality, factual accuracy, AP style, newsworthiness
**Finance:** numerical accuracy, regulatory compliance, risk identification, assumption transparency, decision clarity
**HR/People Ops:** legal compliance, tone appropriateness, policy accuracy, actionability, confidentiality
**Marketing:** brand voice, CTA clarity, audience targeting, channel fit, measurability
**Legal:** clause completeness, ambiguity score, risk exposure, jurisdiction, plain language

### 4. Department DAGs (5 per department × 9 = 45 DAGs)

Each DAG: 3-6 nodes, real prompts, configured models, scored by its department's evals.

**Deep Research (5):**
1. Market Analysis Report
2. Competitive Intelligence Brief
3. Technology Landscape Survey
4. Regulatory Impact Assessment
5. Customer Insight Synthesis

**Product Management (5):**
1. PRD Generator (from vague idea → full spec)
2. Sprint Planning Assistant (backlog → sprint scope)
3. Stakeholder Update Generator
4. Feature Prioritization Framework
5. Release Notes Writer

**Builder/Engineering (5):**
1. Code Review Pipeline (plan → code → review → test)
2. Bug Fix Pipeline (reproduce → diagnose → fix → verify)
3. Architecture Decision Record Generator
4. API Design Pipeline (spec → implementation → docs)
5. Migration Planner (old system → new system)

**Creative Writing — Children's Books (5):**
1. Picture Book (100-300 words, ages 2-5)
2. Early Reader (300-800 words, ages 5-7)
3. Chapter Book Outline (1000-3000 words, ages 7-10)
4. Bedtime Story (200-500 words, calming tone)
5. Educational Story (500-1500 words, teaches a concept)

**Press Releases (5):**
1. Product Launch Announcement
2. Partnership/Collaboration Announcement
3. Executive Appointment
4. Earnings/Financial Results
5. Crisis Communication Statement

**Finance (5):**
1. Budget Variance Analysis
2. Investment Memo
3. Quarterly Forecast Model
4. Cost-Benefit Analysis
5. Risk Assessment Report

**HR/People Ops (5):**
1. Job Description Generator
2. Performance Review Summary
3. Policy Update Communication
4. Onboarding Checklist Generator
5. Exit Interview Synthesis

**Marketing (5):**
1. Campaign Brief Generator
2. Social Media Content Calendar
3. Email Sequence Writer
4. Landing Page Copy
5. Brand Guidelines Enforcer

**Legal (5):**
1. NDA Generator
2. Contract Summary/Plain Language
3. Compliance Checklist
4. Terms of Service Drafter
5. Risk Clause Identifier

### 5. Hill-Climbing Strategy (generalization, not overfitting)

**Per pass:**
- Select 3 evals from the rotation pool (random subset)
- Run DAG → score on those 3
- Propose mutations → validate against those 3
- ALSO check 2 held-out evals (must not regress)
- Accept only if: improves on target AND doesn't regress on held-out

**Across passes:**
- Each pass adds 1 new eval to the rotation pool
- By pass 25: tested against 25+ eval combinations
- Periodic "full sweep" — run ALL evals, report scores
- A DAG is "done" when it scores well on ANY randomly selected eval subset

**Anti-overfitting rules:**
- Never optimize on the same eval combination twice in a row
- Always include at least 1 eval the DAG has never seen
- Track per-eval scores over time — flag if one drops while others rise

### 6. Canvas/Davinci DAG
- Wire the existing layer pipeline as optimizable nodes
- Style Interpreter → Composition Planner → Generator → Compositor → Critic → Refiner → Store
- Eval: visual quality scoring (LLM-as-judge on image descriptions)
- Hill-climb: prompt engineering on style interpreter, model selection on generator

### 7. PM Fleet
- Chatbot model hill-climb (results from today's run)
- Knowledge distillation: Opus answers → focused FAQ → Flash Lite serves
- Jira project key: set to MAISTRO
- Enable GitHub/GitLab tools
- Test topK values (4 vs 8 vs 12)

### 8. UI Awesomeness
- Every page works, nothing stubs
- Grandma mode: chat + buttons, zero config
- Power mode: DAGs, prompts, topology visible
- Multi-user: each user sees their own data
- Real-time: changes reflect immediately
- Mobile-friendly: works on phone
- Accessibility: screen reader compatible
- Onboarding: first-time user guided to value in < 60 seconds
- Error states: never blank, never raw JSON, always helpful
- Speed: every interaction < 200ms (except LLM calls which show real status)

### 9. Deploy to the external deploy platform
- Docker build
- Push to launch-repo
- Verify on preview URL
- Production cutover when ready

---

## Server Start Command
```bash
cd packages/hive-conductor/backend
set -a; source ../../../.env; set +a
export LITELLM_API_BASE="${LITELLM_PROXY_URL}" LITELLM_API_KEY="${LITELLM_PROXY_KEY}" CHAT_DEFAULT_MODEL="gemini-3.5-flash"
export PYTHONPATH="$(pwd):$(pwd)/../../maistro-core/src"
uvicorn main:app --host 0.0.0.0 --port 8101
```

## Key Files Modified Today
- `services/chat_completion.py` — PM agent with real tools
- `services/graph_runner.py` — parallel DAG executor with security tiers
- `services/optimizer.py` — 5-signal + validation gate + rejected buffer
- `services/validation_gate.py` — Pareto-optimal model/param selection
- `services/benchmark_eval.py` — detailed rubric scoring
- `services/skill_optimizer.py` — SkillOpt pattern for skills/tools
- `services/chatbot_integration.py` — Chatbot API client
- `services/eval_judge.py` — expanded mutation vocabulary
- `routes/daily_report_v2.py` — real Jira + Airtable data
- `frontend/src/pages/Chat.tsx` — PM chat with persistence + suggestions
- `frontend/src/pages/Fleet.tsx` — working agent buttons
- `frontend/src/components/AppShell.tsx` — full nav
- `maistro-core/src/maistro/graph/node.py` — JSON schema enforcement

## Credentials
- LiteLLM: preview gateway, key in .env
- Jira: on-prem Jira Server PAT in credential store (atlassian_server_jira)
- Confluence: on-prem Jira Server PAT (atlassian_server_confluence)
- Airtable: PAT in credential store
- Chatbot: browser-use via Chrome debug port (SSO session)
- Hive login: test/user1234

## Rules
1. Don't stop until done
2. If blocked, skip and come back
3. No stubs, no fakes
4. Test all three layers (API, Playwright, browser-use)
5. Commit after each working phase
6. Evals before DAGs — can't hill-climb without knowing "better"
7. Rotate evals — never optimize for the same combo twice
8. Cage before Turing — safety before capability
9. UI last — make it work, then make it pretty
10. Our jobs depend on this being flawless
