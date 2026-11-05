---
title: Connect agent frameworks to models and tools
summary: Point Microsoft Agent Framework, the OpenAI Agents SDK, and LangChain with LangGraph at the gateway's OpenAI-compatible model endpoint and its MCP endpoint, so every model and tool call an agent makes passes through gateway policies and shows up in Monitoring.
category: agents
level: Intermediate
duration: 30
tracks: [code]
order: 15
illustration: diagrams/architecture.svg
tags: [Microsoft Agent Framework, OpenAI Agents SDK, LangChain, LangGraph, MCP, OpenAI-compatible, Python]
objectives:
  - Configure a framework's model client with the gateway's OpenAI-compatible endpoint, an alias, and a runtime key
  - Load governed tools from the gateway's MCP endpoint in each framework
  - Run the same agent in Microsoft Agent Framework, the OpenAI Agents SDK, and LangGraph
  - Prove that the gateway authenticates and records every model and tool call the agent makes
prereqs:
  - 02-first-model-call
  - 04-federate-mcp-tools
---

# Connect agent frameworks to models and tools

Your teams build agents with different frameworks, and each one wires its own model keys and tool servers. Nobody
can say which agent called what, and a policy change means touching every codebase. In this lab you point three
popular frameworks at one gateway: two URLs and one header, and every model and tool call the agent makes is
governed and observable in the same place.

![Agents call models and MCP tools through AI Gateway](../assets/diagrams/architecture.svg "Agents keep their framework. The gateway sits between them and every model and tool they call.")

<!-- widget: request-lifecycle -->

## Before you begin

<!-- setup: tools clone -->

- Complete [Publish a Foundry model and make your first call](../02-first-model-call/README.md). You need the
  gateway URL, a callable alias, and a runtime key. Create a dedicated key for this agent under **Access** ›
  **Keys**, for example `docs-agent`, so its traffic is easy to find.
- Complete [Federate MCP tools behind one endpoint](../04-federate-mcp-tools/README.md). The samples use the
  `learn` MCP server from that lab. Any MCP server on your gateway works.
- Python 3.10 or later. The samples were tested together on Python 3.13 with the versions in
  [infra/requirements.txt](infra/requirements.txt).
- Optional: monitoring from [Monitor usage, cost, and traces](../13-monitoring/README.md), to see the agent's calls.
- Run the scripts and samples from the lab's folder, `~/aigateway/labs/15-agent-frameworks`.

## How it works

Agent frameworks talk to models through an OpenAI-compatible client and to tools through an MCP client. Point both at
the gateway. The model client takes the runtime key as its API key, which it sends as a bearer token that the
model endpoint accepts. The MCP client sends the same key in the `api-key` header, the only place the MCP endpoint
reads it.

The framework still owns orchestration, memory, and state. The gateway authenticates each call, applies the policies
on the alias, the MCP server, and the gateway, routes the alias to its provider, and records telemetry for every call
that leaves the agent. Changing a model, a policy, or a tool list then needs no agent code change.

| Framework | Model client | MCP tools | Model API |
|---|---|---|---|
| Microsoft Agent Framework | `OpenAIChatClient` | `MCPStreamableHTTPTool` | Responses |
| OpenAI Agents SDK | `OpenAIResponsesModel` with `AsyncOpenAI` | `MCPServerStreamableHttp` | Responses |
| LangChain and LangGraph | `ChatOpenAI` with `use_responses_api=True` | `MultiServerMCPClient` (langchain-mcp-adapters) | Responses |

All three use the same two endpoints. The model endpoint also serves Chat Completions, but some reasoning models
only accept function tools on Responses, so the samples use Responses:

- Model: `<gateway-url>/default/models/openai/v1`
- MCP: `<gateway-url>/default/toolservers/<server-name>/mcp`

## Set up the samples

<!-- steps -->

### Install the packages

From the lab folder, create a virtual environment in `infra` and install the pinned packages.

```bash title="Bash"
# Move into the samples folder
cd infra &&
  echo "📂 Samples folder: $(pwd)"

# Create a virtual environment in .venv and activate it, so that the packages stay out of your global Python
python3 -m venv .venv
source .venv/bin/activate &&
  echo "📦 Virtual environment .venv is active"

# Install the pinned packages for Agent Framework, the OpenAI Agents SDK, LangChain, and LangGraph
pip install -r requirements.txt &&
  echo "📦 The packages in requirements.txt are installed"
```

```powershell title="PowerShell"
# Move into the samples folder
cd infra
if ($?) { Write-Host "📂 Samples folder: $(Get-Location)" }

# Create a virtual environment in .venv and activate it, so that the packages stay out of your global Python
python -m venv .venv
.venv\Scripts\Activate.ps1
if ($?) { Write-Host "📦 Virtual environment .venv is active" }

# Install the pinned packages for Agent Framework, the OpenAI Agents SDK, LangChain, and LangGraph
pip install -r requirements.txt
if ($?) { Write-Host "📦 The packages in requirements.txt are installed" }
```

### Configure the environment

Copy `.env.example` to `.env` and fill in your values. The samples build both endpoints from `AI_GATEWAY_URL`. The
[agent access docs](https://ai.gateway.azure.com/docs/agent-access) name the full endpoints
`AI_GATEWAY_MODEL_ENDPOINT` and `AI_GATEWAY_MCP_ENDPOINT`. They point to the same URLs.

<!-- include: infra/.env.example bash -->

On GitHub, open [infra/.env.example](infra/.env.example).

```bash title="Bash"
# Copy the template to .env, then open .env and fill in your four values
cp .env.example .env &&
  echo "📄 .env is ready to fill in"
```

```powershell title="PowerShell"
# Copy the template to .env, then open .env and fill in your four values
Copy-Item .env.example .env
if ($?) { Write-Host "📄 .env is ready to fill in" }
```

> [!IMPORTANT]
> `.env` holds a secret. Keep it out of source control, and in production read the key from your platform's secret
> store or switch to Microsoft Entra ID.

<!-- /steps -->

> **Checkpoint**
> `pip list` shows `agent-framework-core`, `openai-agents`, and `langchain-mcp-adapters`, and `.env` has your four
> values.

## Point the model client at the gateway

Each framework takes the gateway's model endpoint as its base URL, the alias as the model name, and the runtime key
as its API key.

<!-- steps -->

### Configure the model client

```python title="Agent Framework"
# The model endpoint accepts the key as the SDK's bearer token. Adding an api-key header as well gets a 400.
client = OpenAIChatClient(
    model=model,
    base_url=f"{gateway_url}/default/models/openai/v1/",
    api_key=api_key,
)
```

```python title="OpenAI Agents SDK"
client = AsyncOpenAI(
    base_url=f"{gateway_url}/default/models/openai/v1",
    api_key=api_key,
)
# ...
model=OpenAIResponsesModel(model=model, openai_client=client),
```

```python title="LangGraph"
model = ChatOpenAI(
    model=model_name,
    base_url=f"{gateway_url}/default/models/openai/v1",
    api_key=api_key,
    use_responses_api=True,
)
```

Don't add an `api-key` default header to the model client as well: the gateway rejects a request that has both an
`api-key` and an `Authorization` header with `400`.

> [!NOTE]
> The OpenAI Agents SDK sample turns off the SDK's built-in tracing, which otherwise exports traces to OpenAI. The
> gateway already records each model and tool call.

<!-- /steps -->

## Add the gateway's MCP tools

The MCP client connects to one MCP server on the gateway and sends the same key. The agent only sees the tools that
the server publishes, after the gateway's tool controls.

<!-- steps -->

### Connect to the MCP endpoint

```python title="Agent Framework"
mcp_tool = MCPStreamableHTTPTool(
    name="gateway-tools",
    url=f"{gateway_url}/default/toolservers/{server}/mcp",
    static_headers={"api-key": api_key},
    approval_mode="never_require",
    request_timeout=60,
)
```

```python title="OpenAI Agents SDK"
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
```

```python title="LangGraph"
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
```

The `learn` tools only read documentation, so the Agent Framework sample runs them without asking for approval. For
tools that change data, set `approval_mode="always_require"` on the MCP tool and handle the approval requests in your
app. Also narrow the tool list on the gateway, as in
[Control which tools agents can call](../05-mcp-tool-controls/README.md), so every agent gets the same limits.

### Build the agent

```python title="Agent Framework"
async with mcp_tool:
    agent = Agent(client=client, name="docs-agent", instructions=INSTRUCTIONS, tools=mcp_tool)
    result = await agent.run(question)
    print(result.text)
```

```python title="OpenAI Agents SDK"
agent = Agent(
    name="docs-agent",
    instructions=INSTRUCTIONS,
    model=OpenAIResponsesModel(model=model, openai_client=client),
    mcp_servers=[mcp_server],
)
result = await Runner.run(agent, question)
print(result.final_output)
```

```python title="LangGraph"
agent = create_agent(model, tools, system_prompt=INSTRUCTIONS)
result = await agent.ainvoke({"messages": [{"role": "user", "content": question}]})
print(result["messages"][-1].text)
```

`create_agent` from LangChain builds a LangGraph graph that loops between the model and the tools. LangGraph keeps
orchestration and state, while AI Gateway applies policies and records telemetry for every call leaving the agent.

<!-- /steps -->

## Run the agents

<!-- steps -->

### Run each sample

Run the sample for each framework from the `infra` folder, with the virtual environment active. Pass a question as
arguments to override the default one.

```bash title="Agent Framework"
# Run the Agent Framework agent: its model and MCP tool calls both go through the gateway
python agent_framework_agent.py
echo "🤖 The Agent Framework agent's answer is above"
```

```bash title="OpenAI Agents SDK"
# Run the OpenAI Agents SDK agent: its model and MCP tool calls both go through the gateway
python openai_agents_agent.py
echo "🤖 The OpenAI Agents SDK agent's answer is above"
```

```bash title="LangGraph"
# Run the LangGraph agent: its model and MCP tool calls both go through the gateway
python langgraph_agent.py
echo "🤖 The LangGraph agent's answer is above"
```

Expected output: a line such as `Model <model-name> and MCP server learn through <gateway-url>`
(the LangGraph sample also prints how many tools it loaded), then a short answer about AI Gateway that cites
Microsoft Learn URLs. The answer differs between runs and frameworks.

### Review the full samples

<!-- include: infra/agent_framework_agent.py -->

<!-- include: infra/openai_agents_agent.py -->

<!-- include: infra/langgraph_agent.py -->

On GitHub, open [agent_framework_agent.py](infra/agent_framework_agent.py),
[openai_agents_agent.py](infra/openai_agents_agent.py), and [langgraph_agent.py](infra/langgraph_agent.py).

<!-- /steps -->

> **Checkpoint**
> All three samples print an answer that cites at least one `learn.microsoft.com` URL, which means each agent called
> a model and an MCP tool through the gateway.

## Verify

<!-- steps -->

### Prove the gateway is in the path

Run one sample with a wrong key. The gateway rejects the agent's first call with `401`, before any model or tool
runs.

```bash title="Bash"
# Run the LangGraph sample with a wrong key, for this command only, because your shell's value wins over .env
echo "🚦 Expect 401 Unauthorized: the gateway rejects the agent's first call"
AI_GATEWAY_API_KEY="not-a-key" python langgraph_agent.py
```

```powershell title="PowerShell"
# Run the LangGraph sample with a wrong key, then remove it from your shell so that the samples read .env again
Write-Host "🚦 Expect 401 Unauthorized: the gateway rejects the agent's first call"
$env:AI_GATEWAY_API_KEY = "not-a-key"; python langgraph_agent.py; Remove-Item Env:AI_GATEWAY_API_KEY
```

Expected output: a traceback that ends with a `401 Unauthorized` error for the MCP endpoint, because each sample
connects to the MCP server before it calls the model. A key set in your shell takes precedence over `.env`.

### See the agent in Monitoring

If you set up monitoring in [Monitor usage, cost, and traces](../13-monitoring/README.md), wait a few minutes and
open **Monitoring**. On **Overview**, **Model calls** and **Tool calls** both grew. On **Tools**, the `learn`
server shows up in **Usage by tool server**, and **Tool usage by caller identity** shows the agent's key. A run
usually makes at least two model calls: one that asks for a tool and one that writes the answer. Open
**Traces** to see each call with its gateway policies.

<!-- /steps -->

## Go further

- **Give each agent an identity.** Create one runtime key per agent, as in
  [Issue and rotate runtime API keys](../10-api-keys/README.md), so Monitoring and cost limits can tell agents apart.
  For production, drop keys: send a Microsoft Entra token for `https://azure-api.net/aigateway` from the agent's
  managed identity or agent identity, with the **AI Gateway User** role, as in
  [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md).
- **Govern the agent, not the code.** Add a token limit to the alias with
  [Throttle tokens per caller with token limits](../06-token-limits/README.md), or a request rate limit to the MCP
  server. The agent gets `429` responses without any code change, so handle `Retry-After` in long-running agents.
- **Swap models behind the alias.** Retarget the alias to another model or provider, as in
  [Publish models from any provider behind stable aliases](../03-multi-provider-aliases/README.md). The agents keep
  working with the same `AI_GATEWAY_MODEL`.
- **Use .NET.** The [.NET hosted agent sample](https://github.com/Azure-Samples/simple-foundry-hosted-agent-dotnet-aigateway)
  connects Microsoft Agent Framework for .NET to a gateway. With Azure AI Gateway, pass the runtime key as the
  client's API key and don't add an `api-key` header to model calls.
- **Other SDKs.** For the GitHub Copilot SDK and other frameworks, use their model and MCP configuration points with
  the same endpoints, and confirm the endpoint formats and authentication they support.

## Clean up

- Delete `infra/.env`, because it holds a key, and `infra/.venv` if you don't need it.
- If you created a key just for this lab, revoke it under **Access** › **Keys**.

Keep the gateway, the alias, and the `learn` MCP server. Other labs reuse them.

## Next steps

- [Deploy a Foundry hosted agent behind AI Gateway](../16-foundry-hosted-agent/README.md): run an Agent Framework
  agent in Microsoft Foundry with the same gateway wiring.
- [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md): replace the agent's key with an
  identity.
- [Attribute tokens and cost with OpenTelemetry](../14-otel-chargeback/README.md): report each agent's tokens and
  estimated cost.
- Docs: [Connect agents to AI Gateway](https://ai.gateway.azure.com/docs/agent-access)
