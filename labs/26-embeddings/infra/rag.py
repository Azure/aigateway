"""A mini retrieval-augmented generation (RAG) app that runs entirely through AI Gateway: it embeds a few help desk
articles, finds the ones closest to a question with cosine similarity, and asks a chat model to answer from them.
Both models use the same gateway URL and the same runtime key.

Usage:
  pip install -r requirements.txt
  export AI_GATEWAY_URL="<gateway-url>"
  export AI_GATEWAY_MODEL="gpt-5-mini"                          # the chat alias
  export AI_GATEWAY_EMBEDDINGS_MODEL="text-embedding-3-small"   # the embeddings alias
  export AI_GATEWAY_API_KEY="..."      # never commit this value
  python rag.py ["Your question"]
"""

import math
import os
import sys

from openai import OpenAI

gateway_url = os.environ["AI_GATEWAY_URL"].rstrip("/")
chat_model = os.environ.get("AI_GATEWAY_MODEL", "gpt-5-mini")
embeddings_model = os.environ.get("AI_GATEWAY_EMBEDDINGS_MODEL", "text-embedding-3-small")
question = sys.argv[1] if len(sys.argv) > 1 else "My laptop screen cracked. How do I get it fixed, and how long does it take?"

client = OpenAI(
    base_url=f"{gateway_url}/default/models/openai/v1",
    api_key=os.environ["AI_GATEWAY_API_KEY"],
)

ARTICLES = {
    "password": "Reset a forgotten password in the self-service password portal. You need the authenticator app "
    "on your phone. A locked account unlocks by itself after 15 minutes.",
    "laptop-repair": "Report a cracked screen or other laptop damage in the IT portal under Hardware > Repair. "
    "Contoso ships a loaner laptop within two business days, and the repair takes about a week.",
    "vpn": "Connect to the corporate network with the Global Secure Access client. If the client shows "
    "Disconnected, sign out of Windows and sign in again.",
    "new-hire": "New employees get their laptop on their first day. Their manager requests it in the IT portal at "
    "least five business days before the start date.",
    "printers": "Add a printer from Settings > Printers. Floor printers are named after the building and the floor, "
    "for example RED-3.",
    "new-phone": "Before you wipe an old phone, register the authenticator app on the new phone from the security "
    "info page.",
    "software": "Install approved software from Company Portal. Software that isn't listed needs a request with a "
    "business justification.",
    "expenses": "Submit travel expenses within 30 days in the finance portal, with a receipt for every item over "
    "25 USD.",
}


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


# 1. Index: embed every article in one batch. A real app stores these vectors in a vector index.
ids = list(ARTICLES)
indexed = client.embeddings.create(model=embeddings_model, input=[ARTICLES[i] for i in ids])
index = {i: item.embedding for i, item in zip(ids, indexed.data)}
print(f"Indexed:  {len(index)} articles with {embeddings_model}, {indexed.usage.total_tokens} tokens")

# 2. Retrieve: embed the question with the same model, and rank the articles by cosine similarity.
query = client.embeddings.create(model=embeddings_model, input=question).data[0].embedding
ranked = sorted(((cosine(query, vector), i) for i, vector in index.items()), reverse=True)
top = ranked[:2]
print(f"Question: {question}")
for score, article in top:
    print(f"Match:    {score:.3f}  {article}")

# 3. Generate: answer with the chat model, from the retrieved articles only.
context = "\n".join(f"[{article}] {ARTICLES[article]}" for _, article in top)
completion = client.chat.completions.create(
    model=chat_model,
    messages=[
        {
            "role": "system",
            "content": "Answer the question in at most two sentences, using only the articles below. "
            "Cite the article ID in square brackets. If the articles don't answer it, say so.\n\n" + context,
        },
        {"role": "user", "content": question},
    ],
)
print(f"Answer:   {completion.choices[0].message.content}")
print(f"Tokens:   {completion.usage.total_tokens} with {chat_model}" if completion.usage else "")
