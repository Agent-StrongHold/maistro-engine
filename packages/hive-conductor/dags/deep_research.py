"""Deep Research DAGs — 5 multi-node pipelines for research tasks."""

DAGS = [
    {
        "id": "dr_market_analysis",
        "name": "Market Analysis Report",
        "department": "deep_research",
        "description": "Comprehensive market analysis from topic to actionable report",
        "nodes": [
            {"id": "scope", "prompt": "Define the research scope, key questions, and data sources needed for a market analysis on: {input}. Output JSON with fields: topic, questions, sources, timeframe.", "model": "gemini-2.5-flash", "role": "planner"},
            {"id": "gather", "prompt": "Based on this research scope, synthesize available knowledge into structured findings. Include market size, growth rate, key players, and trends. Scope: {scope}", "model": "gemini-2.5-pro", "role": "researcher"},
            {"id": "analyze", "prompt": "Analyze these market findings. Identify patterns, opportunities, threats, and competitive dynamics. Findings: {gather}", "model": "gemini-2.5-pro", "role": "analyst"},
            {"id": "recommend", "prompt": "Based on this analysis, provide 5 actionable recommendations with expected impact and implementation timeline. Analysis: {analyze}", "model": "gemini-2.5-flash", "role": "strategist"},
            {"id": "format", "prompt": "Format this into a professional market analysis report with executive summary, sections, charts descriptions, and appendix. Content: {recommend}", "model": "gemini-2.5-flash", "role": "writer"},
        ],
        "edges": [{"from_node": "scope", "to_node": "gather"}, {"from_node": "gather", "to_node": "analyze"}, {"from_node": "analyze", "to_node": "recommend"}, {"from_node": "recommend", "to_node": "format"}],
        "evals": ["SourceAttribution", "ClaimFactuality", "Completeness", "Synthesis", "Actionability"],
    },
    {
        "id": "dr_competitive_intel",
        "name": "Competitive Intelligence Brief",
        "department": "deep_research",
        "description": "Analyze competitors and produce strategic intelligence brief",
        "nodes": [
            {"id": "identify", "prompt": "Identify the top 5 competitors for: {input}. For each, note their positioning, strengths, and recent moves. Output structured JSON.", "model": "gemini-2.5-flash", "role": "researcher"},
            {"id": "compare", "prompt": "Create a detailed comparison matrix across these competitors on: pricing, features, market share, technology, and customer satisfaction. Competitors: {identify}", "model": "gemini-2.5-pro", "role": "analyst"},
            {"id": "gaps", "prompt": "Identify market gaps and opportunities based on this competitive comparison. Where are competitors weak? What's underserved? Comparison: {compare}", "model": "gemini-2.5-pro", "role": "strategist"},
            {"id": "brief", "prompt": "Write a 2-page competitive intelligence brief with key findings, threat assessment, and recommended counter-strategies. Analysis: {gaps}", "model": "gemini-2.5-flash", "role": "writer"},
        ],
        "edges": [{"from_node": "identify", "to_node": "compare"}, {"from_node": "compare", "to_node": "gaps"}, {"from_node": "gaps", "to_node": "brief"}],
        "evals": ["SourceAttribution", "Synthesis", "Actionability"],
    },
    {
        "id": "dr_tech_landscape",
        "name": "Technology Landscape Survey",
        "department": "deep_research",
        "description": "Survey emerging technologies and assess relevance",
        "nodes": [
            {"id": "scan", "prompt": "Survey the technology landscape for: {input}. Identify emerging technologies, maturity levels (Gartner hype cycle position), and key vendors.", "model": "gemini-2.5-pro", "role": "researcher"},
            {"id": "assess", "prompt": "Assess each technology for: readiness, risk, cost, and strategic fit. Rate each 1-5. Technologies: {scan}", "model": "gemini-2.5-flash", "role": "analyst"},
            {"id": "roadmap", "prompt": "Create a technology adoption roadmap: what to adopt now, pilot next quarter, and watch for later. Assessment: {assess}", "model": "gemini-2.5-flash", "role": "strategist"},
        ],
        "edges": [{"from_node": "scan", "to_node": "assess"}, {"from_node": "assess", "to_node": "roadmap"}],
        "evals": ["Completeness", "ClaimFactuality", "Actionability"],
    },
    {
        "id": "dr_regulatory_impact",
        "name": "Regulatory Impact Assessment",
        "department": "deep_research",
        "description": "Assess regulatory changes and their business impact",
        "nodes": [
            {"id": "identify_regs", "prompt": "Identify relevant regulations and recent/upcoming changes for: {input}. Include jurisdiction, effective dates, and key requirements.", "model": "gemini-2.5-pro", "role": "researcher"},
            {"id": "impact", "prompt": "Assess the business impact of each regulation: compliance cost, operational changes needed, timeline, and penalties for non-compliance. Regulations: {identify_regs}", "model": "gemini-2.5-pro", "role": "analyst"},
            {"id": "plan", "prompt": "Create a compliance action plan with priorities, responsible parties, and deadlines. Impact assessment: {impact}", "model": "gemini-2.5-flash", "role": "planner"},
        ],
        "edges": [{"from_node": "identify_regs", "to_node": "impact"}, {"from_node": "impact", "to_node": "plan"}],
        "evals": ["ClaimFactuality", "Completeness", "Actionability"],
    },
    {
        "id": "dr_customer_insight",
        "name": "Customer Insight Synthesis",
        "department": "deep_research",
        "description": "Synthesize customer data into actionable insights",
        "nodes": [
            {"id": "segment", "prompt": "Define customer segments for: {input}. Include demographics, behaviors, needs, and pain points for each segment.", "model": "gemini-2.5-flash", "role": "researcher"},
            {"id": "journey", "prompt": "Map the customer journey for each segment: awareness, consideration, purchase, retention, advocacy. Identify friction points. Segments: {segment}", "model": "gemini-2.5-pro", "role": "analyst"},
            {"id": "insights", "prompt": "Synthesize key customer insights: what drives loyalty, what causes churn, and what unmet needs exist. Journey maps: {journey}", "model": "gemini-2.5-pro", "role": "strategist"},
            {"id": "actions", "prompt": "Translate insights into 5 specific product/service improvements with expected impact on NPS and retention. Insights: {insights}", "model": "gemini-2.5-flash", "role": "planner"},
        ],
        "edges": [{"from_node": "segment", "to_node": "journey"}, {"from_node": "journey", "to_node": "insights"}, {"from_node": "insights", "to_node": "actions"}],
        "evals": ["Synthesis", "Actionability", "Completeness"],
    },
]
