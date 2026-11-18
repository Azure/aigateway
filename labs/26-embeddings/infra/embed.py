"""Turns sentences into vectors through AI Gateway with the OpenAI Python SDK, then compares them with cosine
similarity. The gateway serves the embedding model at the same OpenAI-compatible base URL as its chat models,
with the same runtime key.

Usage:
  pip install -r requirements.txt
  export AI_GATEWAY_URL="<gateway-url>"
  export AI_GATEWAY_EMBEDDINGS_MODEL="text-embedding-3-small"
  export AI_GATEWAY_API_KEY="..."      # never commit this value
  python embed.py
"""

import math
import os

from openai import OpenAI

gateway_url = os.environ["AI_GATEWAY_URL"].rstrip("/")
model = os.environ.get("AI_GATEWAY_EMBEDDINGS_MODEL", "text-embedding-3-small")

client = OpenAI(
    base_url=f"{gateway_url}/default/models/openai/v1",
    api_key=os.environ["AI_GATEWAY_API_KEY"],
)


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


sentences = [
    "How do I reset my password?",
    "I forgot the credentials I use to sign in.",
    "What's on the cafeteria menu today?",
]

# One call embeds the whole batch: the response has one vector per input, in the same order.
result = client.embeddings.create(model=model, input=sentences)
vectors = [item.embedding for item in result.data]
print(f"Model:       {result.model}")
print(f"Vectors:     {len(vectors)} with {len(vectors[0])} dimensions each")
print(f"Tokens used: {result.usage.total_tokens}")

for other in (1, 2):
    print(f"Similarity:  {cosine(vectors[0], vectors[other]):.3f}  {sentences[0]!r} vs {sentences[other]!r}")

# text-embedding-3 models can return shorter vectors, which take less space in a vector index.
short = client.embeddings.create(model=model, input=sentences[0], dimensions=256)
print(f"Shorter:     {len(short.data[0].embedding)} dimensions with dimensions=256")
