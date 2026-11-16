#!/usr/bin/env bash
# Sends chat requests to one alias, with optional request headers, and counts which backend model answered each one.
# Usage: ./infra/count-models.sh [alias] [requests] ["header: value" ...]
# Example: ./infra/count-models.sh chat 6 "x-workload: research"
# Needs AI_GATEWAY_URL and AI_GATEWAY_API_KEY in the environment, plus curl and jq. PAUSE sets the seconds between requests.
set -euo pipefail

ALIAS="${1:-chat}"
COUNT="${2:-10}"
shift $(( $# < 2 ? $# : 2 ))
PAUSE="${PAUSE:-0.3}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a gateway runtime API key}"

HEADERS=()
for h in "$@"; do HEADERS+=(-H "$h"); done
URL="${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions"
BODY="$(jq -cn --arg m "$ALIAS" '{model: $m, max_completion_tokens: 16,
  messages: [{role: "user", content: "Reply with one word."}]}')"
RESPONSE="$(mktemp)"
TALLY="$(mktemp)"
trap 'rm -f "$RESPONSE" "$TALLY"' EXIT

echo "Sending $COUNT requests with \"model\": \"$ALIAS\"${*:+ and the header${2:+s} $*}"
for i in $(seq 1 "$COUNT"); do
  CODE="$(curl -sS -o "$RESPONSE" -w '%{http_code}' "$URL" ${HEADERS[@]+"${HEADERS[@]}"} \
    -H "Authorization: Bearer $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" -d "$BODY")"
  if [ "$CODE" = "200" ]; then
    SERVED="$(jq -r '.model // "unknown"' "$RESPONSE")"
  else
    SERVED="HTTP $CODE $(jq -r '.error.code // .message // empty' "$RESPONSE" 2>/dev/null || true)"
  fi
  printf '%3d  %s\n' "$i" "$SERVED"
  echo "$SERVED" >> "$TALLY"
  sleep "$PAUSE"
done

echo
echo "Requests per backend model:"
sort "$TALLY" | uniq -c | sort -rn
