"""List, and optionally call, the tools that an AI Gateway MCP server publishes.

Usage:
    export AI_GATEWAY_URL="<gateway-url>"
    export AI_GATEWAY_API_KEY="..."      # never commit this value
    python list_tools.py [server-name] [tool-name] [query]

Examples:
    python list_tools.py learn
    python list_tools.py learn learn_microsoft_docs_search "What is AI Gateway?"

Set AI_GATEWAY_MCP_ENDPOINT to use a full MCP endpoint URL instead of building it from AI_GATEWAY_URL.
"""

import asyncio
import os
import sys

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError


def endpoint(server: str) -> str:
    if os.environ.get("AI_GATEWAY_MCP_ENDPOINT"):
        return os.environ["AI_GATEWAY_MCP_ENDPOINT"]
    base = os.environ.get("AI_GATEWAY_URL")
    if not base:
        sys.exit("Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com")
    return f"{base.rstrip('/')}/default/toolservers/{server}/mcp"


async def main() -> None:
    server = sys.argv[1] if len(sys.argv) > 1 else "learn"
    tool = sys.argv[2] if len(sys.argv) > 2 else None
    query = sys.argv[3] if len(sys.argv) > 3 else "What is Azure AI Gateway?"
    api_key = os.environ.get("AI_GATEWAY_API_KEY")
    if not api_key:
        sys.exit("Set AI_GATEWAY_API_KEY to a runtime key from Access > API keys")

    url = endpoint(server)
    print(f"MCP endpoint: {url}")

    # The gateway authenticates the client with the runtime key in the api-key header.
    async with httpx.AsyncClient(headers={"api-key": api_key}, timeout=60) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (read, write, _):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                print(f"Server: {init.serverInfo.name}  protocol: {init.protocolVersion}\n")

                result = await session.list_tools()
                for t in result.tools:
                    description = " ".join((t.description or "").split())[:70]
                    print(f"{t.name:<45} {description}")
                print(f"\n{len(result.tools)} tools published")

                if tool:
                    print(f"\nCalling {tool} with query: {query}")
                    try:
                        call = await session.call_tool(tool, {"query": query})
                    except McpError as error:
                        print(f"The tool call failed: {error}")
                        return
                    text = "\n".join(c.text for c in call.content if c.type == "text")
                    if call.isError:
                        print(f"The tool call failed: {text}")
                        return
                    print(text[:600] + "\n...")


if __name__ == "__main__":
    asyncio.run(main())
