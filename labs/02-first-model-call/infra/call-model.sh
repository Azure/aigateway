#!/usr/bin/env bash
# Calls a model through AI Gateway twice, once with Chat Completions and once with the Responses API,
# and prints the HTTP status and the model's reply for each call.
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   export AI_GATEWAY_MODEL="<model-name>"
#   export AI_GATEWAY_API_KEY="..."      # never commit this value
#   ./call-model.sh ["Your prompt"]
# Requires curl and jq.
set -euo pipefail

PROMPT="${1:-Write a one-sentence status update.}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_MODEL:?Set AI_GATEWAY_MODEL to the callable model alias}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a runtime key from Access > Keys}"

BASE="${AI_GATEWAY_URL%/}/default/models/openai/v1"

call() {
  local label="$1" path="$2" body="$3" filter="$4" out status reply
  out=$(curl -sS -w '\n%{http_code}' "$BASE$path" \
    -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" -d "$body")
  status="${out##*$'\n'}"
  reply="${out%$'\n'*}"
  if [[ "$status" == 2* ]]; then
    printf '%-17s HTTP %s  %s\n' "$label" "$status" "$(printf '%s' "$reply" | jq -r "$filter")"
  else
    printf '%-17s HTTP %s  %s\n' "$label" "$status" "$reply"
  fi
}

call "Chat Completions" "/chat/completions" \
  "$(jq -n --arg m "$AI_GATEWAY_MODEL" --arg p "$PROMPT" '{model:$m, messages:[{role:"user", content:$p}]}')" \
  '.choices[0].message.content'

call "Responses API" "/responses" \
  "$(jq -n --arg m "$AI_GATEWAY_MODEL" --arg p "$PROMPT" '{model:$m, input:$p}')" \
  '[.output[]? | select(.type == "message") | .content[]? | select(.type == "output_text") | .text] | join("")'
