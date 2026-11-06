"""A Foundry hosted agent whose model calls and MCP tool calls both go through AI Gateway, without keys.

The agent has no Foundry model deployment and no direct route to a tool:
- Model: it calls the gateway's OpenAI-compatible model endpoint with an alias and a Microsoft Entra token for the
  gateway's audience.
- Tools: it calls a Foundry toolbox, which reaches the gateway's MCP server through a RemoteTool connection that signs
  in with the Foundry project's managed identity.

In Foundry, the tokens come from the agent's managed identity. Locally, `azd ai agent run` uses your Azure CLI sign-in.
To run it without azd, copy .env.example to .env, install requirements.txt in a virtual environment, and run
`python main.py`.
"""

import os

import mcp
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework_foundry_hosting import FoundryToolbox, ResponsesHostServer
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

load_dotenv()


class HandshakeClient(mcp.Client):
    """An MCP client that opens its connection with the initialize handshake.

    By default, the MCP SDK negotiates the stateless MCP version 2026-07-28 when the server offers it, and Foundry
    toolboxes do. The toolbox then speaks 2026-07-28 to the gateway's MCP server, and a server that supports only
    earlier versions, like one whose backend is the Microsoft Learn MCP server, answers with HTTP 403. The handshake
    keeps the whole chain on a version that the gateway's MCP server supports.
    """

    def __init__(self, *args, mode: str = "legacy", **kwargs) -> None:
        super().__init__(*args, mode=mode, **kwargs)


# Agent Framework creates its MCP clients from mcp.Client, so this applies to the toolbox connection.
mcp.Client = HandshakeClient

# The audience of AI Gateway's runtime endpoints
AI_GATEWAY_SCOPE = "https://azure-api.net/aigateway/.default"

INSTRUCTIONS = """
You answer questions about Microsoft and Azure technologies.
- Search the Microsoft Learn tools before you answer, and cite the URLs you used.
- Answer from the search results. Fetch a whole article only when they don't answer the question: articles are long,
  and their tokens count toward the model's limits.
- If the tools don't cover the question, say so instead of guessing.
- Keep answers under 150 words.
"""


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Set {name}. With azd, run: azd env set {name} <value>")
    return value


# Foundry sets FOUNDRY_HOSTING_ENVIRONMENT in the agent's container. Locally, skip the managed identity probe, so that
# the credential goes straight to your Azure CLI or azd sign-in.
credential = DefaultAzureCredential(
    exclude_managed_identity_credential=not os.environ.get("FOUNDRY_HOSTING_ENVIRONMENT"),
)


def create_agent() -> Agent:
    gateway_url = required("AI_GATEWAY_URL").rstrip("/")
    model = required("AI_GATEWAY_MODEL")
    get_gateway_token = get_bearer_token_provider(credential, AI_GATEWAY_SCOPE)

    async def gateway_token() -> str:
        return get_gateway_token()

    # The SDK sends the token as Authorization: Bearer, and asks for a fresh one before each call.
    client = OpenAIChatClient(
        model=model,
        base_url=f"{gateway_url}/default/models/openai/v1/",
        api_key=gateway_token,
    )

    # FoundryToolbox reads the toolbox endpoint from TOOLBOX_ENDPOINT, and signs in to Foundry with the same credential.
    tools = FoundryToolbox(credential, timeout=60)

    return Agent(
        client=client,
        name="gateway-docs-agent",
        instructions=INSTRUCTIONS,
        tools=tools,
        # Foundry keeps the conversation history, so the model call doesn't need to store it.
        default_options={"store": False},
    )


if __name__ == "__main__":
    # The server creates the agent for each request, and closes its toolbox connection afterward.
    ResponsesHostServer(agent=create_agent).run()
