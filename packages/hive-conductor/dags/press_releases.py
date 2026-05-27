"""Press Releases DAGs — 5 multi-node pipelines for PR writing."""

DAGS = [
    {
        "id": "pr_product_launch",
        "name": "Product Launch Announcement",
        "department": "press_releases",
        "description": "Full press release for a product launch",
        "nodes": [
            {"id": "facts", "prompt": "Extract key facts for a product launch press release: product name, features, availability, pricing, target audience, quotes needed. Input: {input}", "model": "gemini-2.5-flash", "role": "researcher"},
            {"id": "draft", "prompt": "Write a press release in AP style: dateline, lead (who/what/when/where/why), body (details, quotes, background), boilerplate. Facts: {facts}", "model": "gemini-2.5-pro", "role": "writer"},
            {"id": "polish", "prompt": "Polish: ensure inverted pyramid structure, add compelling quotes, verify AP style compliance, add media contact. Draft: {draft}", "model": "gemini-2.5-flash", "role": "editor"},
        ],
        "edges": [{"from_node": "facts", "to_node": "draft"}, {"from_node": "draft", "to_node": "polish"}],
        "evals": ["InvertedPyramid", "QuoteQuality", "APStyle", "Newsworthiness"],
    },
    {
        "id": "pr_partnership",
        "name": "Partnership/Collaboration Announcement",
        "department": "press_releases",
        "description": "Announce a new partnership or collaboration",
        "nodes": [
            {"id": "context", "prompt": "Gather partnership details: both parties, nature of collaboration, mutual benefits, timeline, and joint goals. Input: {input}", "model": "gemini-2.5-flash", "role": "researcher"},
            {"id": "draft", "prompt": "Write a partnership press release. Include quotes from both parties, specific deliverables, and market impact. Context: {context}", "model": "gemini-2.5-pro", "role": "writer"},
            {"id": "balance", "prompt": "Ensure balanced representation of both parties. Neither should dominate. Add boilerplates for both companies. Draft: {draft}", "model": "gemini-2.5-flash", "role": "editor"},
        ],
        "edges": [{"from_node": "context", "to_node": "draft"}, {"from_node": "draft", "to_node": "balance"}],
        "evals": ["QuoteQuality", "FactualAccuracy", "APStyle"],
    },
    {
        "id": "pr_executive",
        "name": "Executive Appointment",
        "department": "press_releases",
        "description": "Announce a new executive hire or promotion",
        "nodes": [
            {"id": "bio", "prompt": "Structure executive bio: name, new role, previous experience, education, notable achievements, and reporting structure. Input: {input}", "model": "gemini-2.5-flash", "role": "researcher"},
            {"id": "draft", "prompt": "Write executive appointment press release: announcement, CEO quote about the hire, new exec quote about vision, bio paragraph, company boilerplate. Bio: {bio}", "model": "gemini-2.5-pro", "role": "writer"},
            {"id": "tone", "prompt": "Ensure professional tone, no hyperbole, factual claims only. Verify AP style for titles and names. Draft: {draft}", "model": "gemini-2.5-flash", "role": "editor"},
        ],
        "edges": [{"from_node": "bio", "to_node": "draft"}, {"from_node": "draft", "to_node": "tone"}],
        "evals": ["QuoteQuality", "FactualAccuracy", "APStyle", "InvertedPyramid"],
    },
    {
        "id": "pr_earnings",
        "name": "Earnings/Financial Results",
        "department": "press_releases",
        "description": "Quarterly or annual financial results announcement",
        "nodes": [
            {"id": "numbers", "prompt": "Structure financial data: revenue, growth %, EPS, guidance, key metrics, YoY comparisons. Input: {input}", "model": "gemini-2.5-flash", "role": "analyst"},
            {"id": "narrative", "prompt": "Write earnings press release: headline number, CEO commentary, segment breakdown, outlook, and safe harbor statement. Data: {numbers}", "model": "gemini-2.5-pro", "role": "writer"},
            {"id": "compliance", "prompt": "Verify: safe harbor language present, no forward-looking statements without disclaimer, numbers consistent, proper SEC formatting. Draft: {narrative}", "model": "gemini-2.5-flash", "role": "editor"},
        ],
        "edges": [{"from_node": "numbers", "to_node": "narrative"}, {"from_node": "narrative", "to_node": "compliance"}],
        "evals": ["FactualAccuracy", "APStyle", "Newsworthiness"],
    },
    {
        "id": "pr_crisis",
        "name": "Crisis Communication Statement",
        "department": "press_releases",
        "description": "Rapid response crisis communication",
        "nodes": [
            {"id": "assess", "prompt": "Assess the crisis: what happened, who's affected, current status, what's being done. Input: {input}", "model": "gemini-2.5-flash", "role": "analyst"},
            {"id": "draft", "prompt": "Write crisis statement: acknowledge the situation, express concern, state actions taken, commit to transparency, provide contact. Assessment: {assess}", "model": "gemini-2.5-pro", "role": "writer"},
            {"id": "legal_review", "prompt": "Review for legal risk: no admission of liability, no speculation, factual only, appropriate empathy without blame. Draft: {draft}", "model": "gemini-2.5-flash", "role": "reviewer"},
        ],
        "edges": [{"from_node": "assess", "to_node": "draft"}, {"from_node": "draft", "to_node": "legal_review"}],
        "evals": ["FactualAccuracy", "APStyle", "QuoteQuality"],
    },
]
