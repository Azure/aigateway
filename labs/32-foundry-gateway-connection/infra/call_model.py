"""Call an AI Gateway model through a Foundry project's gateway connection, directly and from a Foundry agent.

Reads FOUNDRY_PROJECT_ENDPOINT (https://<foundry resource>.services.ai.azure.com/api/projects/<project>) and
FOUNDRY_MODEL (<connection name>/<alias>). Signs in with DefaultAzureCredential, so `az login` or `azd auth login`
is enough: Foundry calls the gateway with the project's managed identity, and no key leaves the gateway.

    python infra/call_model.py             # ask the model, then create, ask, and delete a Foundry agent
    python infra/call_model.py --burst 6   # send 6 requests in a row to see the gateway's token limit
"""

import argparse
import os
import sys

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential
from openai import APIStatusError

QUESTION = "In one sentence, what does an AI gateway do for an app team?"
AGENT_QUESTION = "Why route an agent's model calls through a gateway?"
AGENT_NAME = "gateway-helper-sdk"
INSTRUCTIONS = "You answer in one short sentence."


def settings() -> tuple[str, str]:
    missing = [name for name in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL") if not os.environ.get(name)]
    if missing:
        sys.exit(f"Set {', '.join(missing)} in your shell. See the lab's Call the model section.")
    return os.environ["FOUNDRY_PROJECT_ENDPOINT"], os.environ["FOUNDRY_MODEL"]


def make_project(endpoint: str) -> AIProjectClient:
    return AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())


def ask(openai, model: str, question: str = QUESTION):
    # The project's OpenAI client serves the Responses API. The model is <connection name>/<alias>.
    return openai.responses.create(model=model, input=question)


def create_agent(project: AIProjectClient, model: str, name: str = AGENT_NAME):
    return project.agents.create_version(
        agent_name=name,
        definition=PromptAgentDefinition(model=model, instructions=INSTRUCTIONS),
    )


def ask_agent(openai, agent, question: str = AGENT_QUESTION):
    return openai.responses.create(
        input=question,
        extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
    )


def burst(openai, model: str, count: int) -> list[tuple[int, int | None, str]]:
    """Send count requests in a row and return (status, total tokens, error message) for each."""
    # The OpenAI client retries a 429 twice by default. Turn that off, so that each 429 shows up right away.
    openai = openai.with_options(max_retries=0)
    results = []
    for _ in range(count):
        try:
            response = ask(openai, model)
            results.append((200, response.usage.total_tokens, ""))
        except APIStatusError as error:
            # Keep Foundry's message and the gateway's, and drop the request ID and the quota link after them
            results.append((error.status_code, None, str(error.message).split(" Request ID")[0]))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--burst", type=int, metavar="N", help="send N requests in a row and print each status")
    args = parser.parse_args()

    endpoint, model = settings()
    project = make_project(endpoint)
    openai = project.get_openai_client()

    if args.burst:
        for number, (status, tokens, message) in enumerate(burst(openai, model, args.burst), start=1):
            print(f"{number}: {status} {f'{tokens} tokens' if tokens else message}")
        return

    response = ask(openai, model)
    print(f"🤖 {response.model}: {response.output_text}")

    agent = create_agent(project, model)
    try:
        reply = ask_agent(openai, agent)
        print(f"🤖 {agent.name} (version {agent.version}): {reply.output_text}")
    finally:
        project.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
        print(f"🚮 Deleted agent {agent.name} version {agent.version}")


if __name__ == "__main__":
    main()
