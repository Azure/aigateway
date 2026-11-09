#!/usr/bin/env bash
# Sends chat requests to one alias and counts which backend model answered each one.
# Usage: ./infra/count-models.sh [alias] [requests] [pause-seconds]
# Needs AI_GATEWAY_URL and AI_GATEWAY_API_KEY in the environment, plus curl and jq.
set -euo pipefail

ALIAS="${1:-chat}"
COUNT="${2:-20}"
PAUSE="${3:-0.5}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a gateway runtime API key}"

URL="${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions"
BODY="$(jq -cn --arg m "$ALIAS" '{model: $m, max_completion_tokens: 16,
  messages: [{role: "user", content: "Reply with one word."}]}')"
RESPONSE="$(mktemp)"
TALLY="$(mktemp)"
trap 'rm -f "$RESPONSE" "$TALLY"' EXIT

echo "Sending $COUNT requests with \"model\": \"$ALIAS\""
for i in $(seq 1 "$COUNT"); do
  CODE="$(curl -sS -o "$RESPONSE" -w '%{http_code}' "$URL" \
    -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" -d "$BODY")"
  if [ "$CODE" = "200" ]; then
    SERVED="$(jq -r '.model // "unknown"' "$RESPONSE")"
  else
    SERVED="HTTP $CODE $(jq -r '.error.code // empty' "$RESPONSE" 2>/dev/null || true)"
  fi
  printf '%3d  %s\n' "$i" "$SERVED"
  echo "$SERVED" >> "$TALLY"
  sleep "$PAUSE"
done

echo
echo "Requests per backend model:"
sort "$TALLY" | uniq -c | sort -rn
