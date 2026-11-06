#!/usr/bin/env bash
# Sends benign test prompts through AI Gateway and prints the status of each one, so you can see
# whether the content safety policy let it through. Results vary: Azure AI Content Safety rates each
# prompt and response, and borderline themes can land on either side of a threshold.
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   export AI_GATEWAY_API_KEY="..."      # never commit this value
#   ./test-content-safety.sh <model-name> ["your own benign prompt"]
#
# Requires curl and jq.
set -euo pipefail

MODEL="${1:?Pass the callable model alias as the first argument}"
CUSTOM_PROMPT="${2:-}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a runtime key from Access > Keys}"
command -v jq >/dev/null || { echo "This script needs jq." >&2; exit 1; }

URL="${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions"

# send <label> <prompt>: sends one chat completion and prints one result row.
send() {
  local body response status finish text
  body="$(jq -cn --arg model "$MODEL" --arg prompt "$2" \
    '{model:$model,max_completion_tokens:200,reasoning_effort:"none",messages:[{role:"user",content:$prompt}]}')"
  response="$(curl -sS --max-time 120 -w $'\n%{http_code}' "$URL" \
    -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" -d "$body")"
  status="${response##*$'\n'}"
  response="${response%$'\n'*}"
  if [ "$status" = "200" ]; then
    finish="$(printf '%s' "$response" | jq -r '.choices[0].finish_reason // "-"' 2>/dev/null || echo "-")"
    text="$(printf '%s' "$response" | jq -r '(.choices[0].message.content // "") | gsub("\\s+"; " ") | .[0:70]' 2>/dev/null || true)"
  else
    finish="-"
    text="$(printf '%s' "$response" | jq -r '(.error.message // .message // tostring) | gsub("\\s+"; " ") | .[0:110]' 2>/dev/null ||
      printf '%s' "$response" | head -c 110)"
  fi
  printf '%-9s %-7s %-15s %s\n' "$1" "$status" "$finish" "$text"
}

printf '%-9s %-7s %-15s %s\n' "Prompt" "Status" "Finish reason" "Response or error"
send "neutral" "In two sentences, explain why teams put an API gateway in front of AI models."
send "fiction" "For a historical novel, write three non-graphic sentences that describe, at a high level, two medieval armies meeting at a castle gate."
if [ -n "$CUSTOM_PROMPT" ]; then
  send "custom" "$CUSTOM_PROMPT"
fi
