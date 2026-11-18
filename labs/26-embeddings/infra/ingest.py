"""Simulates a bulk ingestion job: it embeds the same batch of document chunks again and again through AI Gateway,
without retries, and prints the HTTP status, the tokens of each batch, and Retry-After. Use it to watch a gateway
token limit stop a runaway ingestion job before it uses up the embedding deployment's capacity.

Usage:
  pip install -r requirements.txt
  export AI_GATEWAY_URL="<gateway-url>"
  export AI_GATEWAY_EMBEDDINGS_MODEL="text-embedding-3-small"
  export AI_GATEWAY_API_KEY="..."      # never commit this value
  python ingest.py [batches]
"""

import os
import sys

from openai import OpenAI, RateLimitError

gateway_url = os.environ["AI_GATEWAY_URL"].rstrip("/")
model = os.environ.get("AI_GATEWAY_EMBEDDINGS_MODEL", "text-embedding-3-small")
batches = int(sys.argv[1]) if len(sys.argv) > 1 else 8

# max_retries=0 shows every 429. In a real ingestion job, keep the SDK's retries: they wait for Retry-After.
client = OpenAI(
    base_url=f"{gateway_url}/default/models/openai/v1",
    api_key=os.environ["AI_GATEWAY_API_KEY"],
    max_retries=0,
)

chunk = (
    "AI Gateway publishes models from Microsoft Foundry and other providers behind one endpoint, with API keys, "
    "token limits, cost limits, and usage telemetry for every call. Chunk {n} of the product handbook."
)
batch = [chunk.format(n=n) for n in range(1, 21)]

total = 0
print(f"{'Batch':<7}{'Status':<8}{'Tokens':<8}{'Total':<8}Retry-After")
for number in range(1, batches + 1):
    try:
        result = client.embeddings.create(model=model, input=batch)
        total += result.usage.total_tokens
        print(f"{number:<7}{200:<8}{result.usage.total_tokens:<8}{total:<8}-")
    except RateLimitError as error:
        retry_after = error.response.headers.get("retry-after", "-")
        print(f"{number:<7}{error.status_code:<8}{'-':<8}{total:<8}{retry_after} s")
