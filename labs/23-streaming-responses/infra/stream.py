"""Streams a reply through AI Gateway with the OpenAI Python SDK: once with Chat Completions and once with the
Responses API. Each stream prints text as it arrives and then the token usage from the end of the stream.

Usage:
  pip install -r requirements.txt
  export AI_GATEWAY_URL="<gateway-url>"
  export AI_GATEWAY_MODEL="<model-name>"
  export AI_GATEWAY_API_KEY="..."      # never commit this value
  python stream.py
"""

import os
import time

from openai import OpenAI

gateway_url = os.environ["AI_GATEWAY_URL"].rstrip("/")
model = os.environ["AI_GATEWAY_MODEL"]

client = OpenAI(
    base_url=f"{gateway_url}/default/models/openai/v1",
    api_key=os.environ["AI_GATEWAY_API_KEY"],
)

print("Chat Completions:")
started = time.perf_counter()
first_token = None
usage = None
stream = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Explain in two sentences why streaming makes chat apps feel faster."}],
    stream=True,
    # Ask for a final usage chunk. It arrives with an empty choices array, just before the stream ends.
    stream_options={"include_usage": True},
)
for chunk in stream:
    if chunk.usage:
        usage = chunk.usage
    # The first chunk (prompt filter results) and the usage chunk have no choices.
    if not chunk.choices:
        continue
    text = chunk.choices[0].delta.content
    if text:
        first_token = first_token or time.perf_counter() - started
        print(text, end="", flush=True)
print(f"\nFirst token:      {first_token:.2f} s" if first_token else "\nFirst token:      -")
print(f"Tokens used:      {usage.total_tokens} (prompt {usage.prompt_tokens}, completion {usage.completion_tokens})"
      if usage else "Tokens used:      no usage chunk")

print("\nResponses API:")
events = client.responses.create(
    model=model,
    input="Write a one-sentence status update about streaming.",
    stream=True,
)
for event in events:
    if event.type == "response.output_text.delta":
        print(event.delta, end="", flush=True)
    elif event.type == "response.completed":
        # The Responses API always reports usage in its final event.
        done = event.response.usage
        print(f"\nTokens used:      {done.total_tokens} (input {done.input_tokens}, output {done.output_tokens})")
