"""Runs a GitHub Copilot SDK agent session on gpt-6.1-sol published by Azure AI Gateway (bring your own key).

Set AI_GATEWAY_URL and AI_GATEWAY_API_KEY first. No GitHub sign-in is needed: every model call goes to the gateway.
Set AI_GATEWAY_MCP_URL too, and the agent also gets the tools of an MCP server that the gateway publishes.
"""

import asyncio
import os
import sys

from copilot import CopilotClient, PermissionHandler


async def main() -> None:
    gateway_url = os.environ["AI_GATEWAY_URL"].rstrip("/")
    api_key = os.environ["AI_GATEWAY_API_KEY"]
    model = os.environ.get("AI_GATEWAY_MODEL", "gpt-6.1-sol")
    mcp_url = os.environ.get("AI_GATEWAY_MCP_URL")

    # MCP endpoints read the key from the api-key header. Model calls send it as a bearer token.
    mcp_servers = (
        {"ai-gateway-learn": {"type": "http", "url": mcp_url, "headers": {"api-key": api_key}, "tools": ["*"]}}
        if mcp_url
        else {}
    )

    client = CopilotClient()
    await client.start()
    try:
        session = await client.create_session(
            model=model,
            provider={
                "type": "openai",
                "base_url": f"{gateway_url}/default/models/openai/v1",
                "api_key": api_key,
                "wire_api": "responses",
            },
            mcp_servers=mcp_servers,
            on_permission_request=PermissionHandler.approve_all,
        )
        prompt = " ".join(sys.argv[1:]) or "Which model are you? Then list the files in this folder."
        reply = await session.send_and_wait(prompt, timeout=180)
        print(reply.data.content if reply else "(no reply)")
        await session.disconnect()
    finally:
        await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
