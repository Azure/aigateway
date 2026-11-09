"""Calls a model through AI Gateway with a Microsoft Entra ID access token instead of an API key.

DefaultAzureCredential picks up your Azure CLI or Visual Studio Code sign-in on a laptop, and a managed
identity or workload identity when the code runs in Azure. The token provider returns a cached token and
refreshes it before it expires. The OpenAI SDK (1.106 or later) calls the provider before every request and
sends the result as `Authorization: Bearer <token>`.

Usage:
  pip install -r requirements.txt
  az login
  export AI_GATEWAY_URL="<gateway-url>"
  export AI_GATEWAY_MODEL="<model-name>"
  python call_with_entra.py
"""

import os

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI

# App-only and managed identity callers must use /.default. It also works for an Azure CLI sign-in.
AI_GATEWAY_SCOPE = "https://azure-api.net/aigateway/.default"

gateway_url = os.environ["AI_GATEWAY_URL"].rstrip("/")
model = os.environ["AI_GATEWAY_MODEL"]

token_provider = get_bearer_token_provider(DefaultAzureCredential(), AI_GATEWAY_SCOPE)

client = OpenAI(
    base_url=f"{gateway_url}/default/models/openai/v1",
    api_key=token_provider,
)

completion = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "In one sentence, why use Microsoft Entra ID instead of API keys?"}],
)
print(f"Model reply: {completion.choices[0].message.content}")
print(f"Tokens used: {completion.usage.total_tokens if completion.usage else 'n/a'}")
