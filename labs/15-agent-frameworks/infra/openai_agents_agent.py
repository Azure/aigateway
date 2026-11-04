"""An OpenAI Agents SDK agent whose model and MCP tool calls both go through AI Gateway.

The agent uses the Responses model class with an AsyncOpenAI client pointed at the gateway's
OpenAI-compatible endpoint, and an MCP server connection to the gateway's MCP endpoint. The client sends the runtime
key as its API key, and the MCP connection sends it in the api-key header.

Usage:
    cp .env.example .env      # then fill in the values
    python openai_agents_agent.py ["your question"]
"""

import asyncio
import os
import sys

from agents import Agent, OpenAIResponsesModel, Runner, set_tracing_disabled
from agents.mcp import MCPServerStreamableHttp
from dotenv import load_dotenv
from openai import AsyncOpenAI

INSTRUCTIONS = (
    "You answer questions about Microsoft technologies. Use the Microsoft Learn tools to find current "
    "documentation and cite the URLs you used. Keep answers under 120 words."
)
QUESTION = "What is Azure AI Gateway? Answer in three bullet points."


def settings() -> tuple[str, str, str, str]:
    load_dotenv()
    missing = [name for name in ("AI_GATEWAY_URL", "AI_GATEWAY_MODEL", "AI_GATEWAY_API_KEY") if not os.environ.get(name)]
    if missing:
        sys.exit(f"Set {', '.join(missing)} in .env or your shell. See .env.example.")
    gateway_url = os.environ["AI_GATEWAY_URL"].rstrip("/")
    server = os.environ.get("AI_GATEWAY_MCP_SERVER", "learn")
    return gateway_url, os.environ["AI_GATEWAY_MODEL"], os.environ["AI_GATEWAY_API_KEY"], server


async def main() -> None:
    gateway_url, model, api_key, server = settings()
    question = " ".join(sys.argv[1:]) or QUESTION

    # The SDK exports its own traces to OpenAI by default. AI Gateway already records every model and tool call.
    set_tracing_disabled(True)

    client = AsyncOpenAI(
        base_url=f"{gateway_url}/default/models/openai/v1",
        api_key=api_key,
    )

    async with MCPServerStreamableHttp(
        name="gateway-tools",
        params={
            "url": f"{gateway_url}/default/toolservers/{server}/mcp",
            "headers": {"api-key": api_key},
            "timeout": 60,
        },
        cache_tools_list=True,
        client_session_timeout_seconds=60,
    ) as mcp_server:
        agent = Agent(
            name="docs-agent",
            instructions=INSTRUCTIONS,
            model=OpenAIResponsesModel(model=model, openai_client=client),
            mcp_servers=[mcp_server],
        )
        print(f"Model {model} and MCP server {server} through {gateway_url}\n")
        result = await Runner.run(agent, question)
        print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
