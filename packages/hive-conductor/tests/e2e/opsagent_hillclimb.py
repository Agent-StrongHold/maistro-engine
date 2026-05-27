"""OpsAgent hill-climber — tests models, params, and settings via browser-use.

Runs the same test questions against different configurations,
scores each response, picks the Pareto-optimal config.
"""
import asyncio
import json
import os
import time

os.environ['OPENAI_API_KEY'] = 'sk-NFdRTYsn3lWfIsJZBhhdbA'
os.environ['OPENAI_BASE_URL'] = 'https://preview.jedai-gateway.wdprapps.disney.com/v1'

from browser_use import Agent, Browser
from browser_use import ChatOpenAI

llm = ChatOpenAI(model='gemini-3.5-flash')

# Test questions that cover different capabilities
TEST_QUESTIONS = [
    "What is JedAI v2?",
    "How do I get an API key?",
    "Can I use PII data with JedAI?",
]

# Configs to test (model + settings changes via the OpsAgent UI)
CONFIGS_TO_TEST = [
    {"name": "baseline (claude-opus-4-6)", "model": None},  # don't change, just measure
    {"name": "claude-sonnet-4-6", "model": "claude-sonnet-4-6"},
    {"name": "gemini-2.5-flash", "model": "gemini-2.5-flash"},
    {"name": "gpt-5-mini", "model": "gpt-5-mini"},
    {"name": "claude-haiku-4-5", "model": "claude-haiku-4-5"},
]


async def change_model(browser, model_name):
    """Change the model in OpsAgent config via the UI."""
    agent = Agent(
        task=f'Go to https://latest.opsagent.wdprapps.disney.com/teams/jedai_team. Click the "Configuration" tab. Find the AI Model selector. Change it to "{model_name}". Save the configuration.',
        llm=llm,
        browser=browser,
        max_steps=10,
    )
    await agent.run()


async def ask_question(browser, question):
    """Ask a question and get the response with timing."""
    start = time.time()
    agent = Agent(
        task=f'In the Ops Agent chat overlay, type: "{question}" and send it. Wait for the complete response. Copy the full response text.',
        llm=llm,
        browser=browser,
        max_steps=15,
    )
    result = await agent.run()
    elapsed = time.time() - start

    response = ""
    try:
        response = result.final_result()
    except:
        pass

    return {"question": question, "response": response[:1000], "latency_s": elapsed}


async def score_response(question, response):
    """Score a response using LLM-as-judge."""
    import httpx
    messages = [
        {"role": "system", "content": "Score this chatbot response 1-10 on: accuracy, completeness, actionability. Return JSON: {\"accuracy\": N, \"completeness\": N, \"actionability\": N, \"total\": N}"},
        {"role": "user", "content": f"Question: {question}\nResponse: {response[:800]}"},
    ]
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://preview.jedai-gateway.wdprapps.disney.com/v1/chat/completions",
            headers={"Authorization": "Bearer sk-NFdRTYsn3lWfIsJZBhhdbA", "Content-Type": "application/json"},
            json={"model": "gemini-3.5-flash", "messages": messages, "response_format": {"type": "json_object"}},
        )
        if r.status_code == 200:
            return json.loads(r.json()["choices"][0]["message"]["content"])
    return {"accuracy": 0, "completeness": 0, "actionability": 0, "total": 0}


async def main():
    browser = Browser(cdp_url='http://localhost:9222')
    results = []

    for config in CONFIGS_TO_TEST:
        print(f"\n{'='*60}")
        print(f"Testing: {config['name']}")
        print(f"{'='*60}")

        # Change model if needed
        if config["model"]:
            print(f"  Switching model to {config['model']}...")
            await change_model(browser, config["model"])
            await asyncio.sleep(3)

        # Ask test questions
        config_scores = []
        for q in TEST_QUESTIONS:
            print(f"  Q: {q[:40]}...")
            resp = await ask_question(browser, q)
            score = await score_response(q, resp["response"])
            resp["score"] = score
            config_scores.append(resp)
            print(f"    Score: {score.get('total', 0)}/30 | Latency: {resp['latency_s']:.1f}s")

        avg_score = sum(r["score"].get("total", 0) for r in config_scores) / len(config_scores)
        avg_latency = sum(r["latency_s"] for r in config_scores) / len(config_scores)

        results.append({
            "config": config["name"],
            "model": config["model"] or "claude-opus-4-6",
            "avg_score": avg_score,
            "avg_latency_s": avg_latency,
            "responses": config_scores,
        })
        print(f"  → AVG Score: {avg_score:.1f}/30 | AVG Latency: {avg_latency:.1f}s")

    # Restore baseline model
    print("\nRestoring baseline model...")
    await change_model(browser, "claude-opus-4-6")

    # Print leaderboard
    print(f"\n{'='*60}")
    print("LEADERBOARD (sorted by score/cost efficiency)")
    print(f"{'='*60}")
    MODEL_COST = {"claude-opus-4-6": 3.0, "claude-sonnet-4-6": 1.5, "gemini-2.5-flash": 0.15, "gpt-5-mini": 0.15, "claude-haiku-4-5": 0.25}
    for r in sorted(results, key=lambda x: x["avg_score"] / MODEL_COST.get(x["model"], 1.0), reverse=True):
        cost = MODEL_COST.get(r["model"], 1.0)
        efficiency = r["avg_score"] / cost
        print(f"  {r['config']:30s} | Score: {r['avg_score']:5.1f} | Latency: {r['avg_latency_s']:5.1f}s | Cost: ${cost} | Efficiency: {efficiency:.1f}")

    # Save full results
    with open("/tmp/opsagent_hillclimb.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to /tmp/opsagent_hillclimb.json")


if __name__ == "__main__":
    asyncio.run(main())
