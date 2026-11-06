"""A Microsoft Agent Framework agent whose model and MCP tool calls both go through AI Gateway.

An OpenAIChatClient (Responses API) points at the gateway's OpenAI-compatible endpoint and sends the runtime key as
its API key. Tools come from the gateway's MCP endpoint for one MCP server, with the key in the api-key header.

Usage:
    cp .env.example .env      # then fill in the values
    python agent_framework_agent.py ["your question"]
"""

import asyncio
import os
import sys

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

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

    # The model endpoint accepts the key as the SDK's bearer token. Adding an api-key header as well gets a 400.
    client = OpenAIChatClient(
        model=model,
        base_url=f"{gateway_url}/default/models/openai/v1/",
        api_key=api_key,
    )

    mcp_tool = MCPStreamableHTTPTool(
        name="gateway-tools",
        url=f"{gateway_url}/default/toolservers/{server}/mcp",
        static_headers={"api-key": api_key},
        approval_mode="never_require",
        request_timeout=60,
    )

    async with mcp_tool:
        agent = Agent(client=client, name="docs-agent", instructions=INSTRUCTIONS, tools=mcp_tool)
        print(f"Model {model} and MCP server {server} through {gateway_url}\n")
        result = await agent.run(question)
        print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
