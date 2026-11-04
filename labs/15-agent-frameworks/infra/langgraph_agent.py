"""A LangChain agent (built on LangGraph) whose model and MCP tool calls both go through AI Gateway.

ChatOpenAI points at the gateway's OpenAI-compatible endpoint, and langchain-mcp-adapters loads tools from the
gateway's MCP endpoint over streamable HTTP. The model takes the runtime key as its API key, and the MCP client
sends it in the api-key header. LangGraph keeps orchestration and state; the gateway applies policies and records
telemetry for every call that leaves the agent.

Usage:
    cp .env.example .env      # then fill in the values
    python langgraph_agent.py ["your question"]
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI

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
    gateway_url, model_name, api_key, server = settings()
    question = " ".join(sys.argv[1:]) or QUESTION

    model = ChatOpenAI(
        model=model_name,
        base_url=f"{gateway_url}/default/models/openai/v1",
        api_key=api_key,
        use_responses_api=True,
    )

    mcp_client = MultiServerMCPClient(
        {
            "gateway-tools": {
                "transport": "streamable_http",
                "url": f"{gateway_url}/default/toolservers/{server}/mcp",
                "headers": {"api-key": api_key},
            }
        }
    )
    tools = await mcp_client.get_tools()

    agent = create_agent(model, tools, system_prompt=INSTRUCTIONS)
    print(f"Model {model_name} and MCP server {server} ({len(tools)} tools) through {gateway_url}\n")
    result = await agent.ainvoke({"messages": [{"role": "user", "content": question}]})
    print(result["messages"][-1].text)


if __name__ == "__main__":
    asyncio.run(main())
