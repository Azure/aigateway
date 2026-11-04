#!/usr/bin/env bash
# Sends one chat completion through AI Gateway and prints the status code, so you can check how the
# gateway-wide baseline treats a call from this machine: 200 when it passes, 403 when the IP filter
# drops it, 429 when a rate limit applies, or 400 when content safety blocks it.
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   export AI_GATEWAY_API_KEY="..."      # never commit this value
#   ./check-call.sh <model-name>
#
# Requires curl and jq.
set -euo pipefail

MODEL="${1:?Pass the callable model alias as the first argument}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a runtime key from Access > Keys}"
command -v jq >/dev/null || { echo "This script needs jq." >&2; exit 1; }

URL="${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions"
BODY="$(jq -cn --arg model "$MODEL" \
  '{model:$model,max_completion_tokens:60,reasoning_effort:"none",messages:[{role:"user",content:"In one sentence, what is a gateway-wide policy baseline?"}]}')"

response="$(curl -sS --max-time 120 -w $'\n%{http_code}' "$URL" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" -d "$BODY")"
status="${response##*$'\n'}"
response="${response%$'\n'*}"

echo "Status: $status"
if [ "$status" = "200" ]; then
  printf '%s' "$response" | jq -r '"Reply:  " + ((.choices[0].message.content // "") | gsub("\\s+"; " "))' 2>/dev/null || true
else
  echo "Body:   $(printf '%s' "$response" | jq -c '.' 2>/dev/null || printf '%s' "$response" | head -c 400)"
fi
