"""Test OpsAgent chatbot via browser-use — asks questions, captures responses."""

import asyncio
import json
import os

from browser_use import Agent, Browser

# Use LiteLLM gateway for the vision model
os.environ.setdefault("OPENAI_API_KEY", os.environ.get("LITELLM_API_KEY", ""))
os.environ.setdefault(
    "OPENAI_BASE_URL",
    os.environ.get("LITELLM_API_BASE", "").rstrip("/") + "/v1"
    if os.environ.get("LITELLM_API_BASE")
    else "",
)

SWAGGER_URL = "https://latest.opsagent.wdprapps.disney.com/api/v1/api-docs/index.html"
TEAM_URL = "https://latest.opsagent.wdprapps.disney.com/teams/jedai_team"

QUESTIONS = [
    "What is JedAI v2?",
    "How do I get access to the JedAI gateway?",
    "What models are available on JedAI?",
    "What is the difference between v1 and v2?",
    "My API call is returning a 401 error, what should I check?",
]


async def main():
    browser = Browser()
    from browser_use import ChatGoogle

    llm = ChatGoogle(model="gemini-3.5-flash")

    results = []

    for q in QUESTIONS:
        print(f"\n{'=' * 60}")
        print(f"Q: {q}")
        print(f"{'=' * 60}")

        agent = Agent(
            task=f"""Go to {TEAM_URL}. 
            If there's a login page, log in (you should already be authenticated via SSO).
            Find the chat input area and type: "{q}"
            Send the message and wait for the response.
            Copy the full response text and report it back to me.
            If you can't find a chat input, try the Swagger UI at {SWAGGER_URL} instead:
            - Find POST /chatbot/chat
            - Click "Try it out"
            - Set message to "{q}" and team_id to "jedai_team"
            - Execute
            - Get the job_id from the response
            - Then use GET /chatbot/chat/{{jobId}} to poll until status is COMPLETED
            - Report the response text
            """,
            llm=llm,
            browser=browser,
        )
        result = await agent.run()
        print(f"A: {result}")
        results.append({"question": q, "response": str(result)})

    await browser.close()

    # Save results
    with open("/tmp/opsagent_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\n\nResults saved to /tmp/opsagent_test_results.json")


if __name__ == "__main__":
    asyncio.run(main())
