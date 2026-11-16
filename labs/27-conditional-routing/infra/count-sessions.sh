#!/usr/bin/env bash
# Sends a few chat requests per session to one alias, each with a session-id header, and prints the backend model
# that served each request, so you can see whether every session stays on one backend model.
# Usage: ./infra/count-sessions.sh [alias] [requests-per-session] [session ...]
# Example: ./infra/count-sessions.sh chat 4 alpha bravo charlie none
# The session name "none" sends no session-id header. SESSION_HEADER changes the header name, PAUSE the seconds between requests.
# Needs AI_GATEWAY_URL and AI_GATEWAY_API_KEY in the environment, plus curl and jq.
set -euo pipefail

ALIAS="${1:-chat}"
COUNT="${2:-4}"
shift $(( $# < 2 ? $# : 2 ))
if [ $# -gt 0 ]; then SESSIONS=("$@"); else SESSIONS=(alpha bravo charlie delta echo foxtrot none); fi
HEADER="${SESSION_HEADER:-session-id}"
PAUSE="${PAUSE:-0.3}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a gateway runtime API key}"

URL="${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions"
BODY="$(jq -cn --arg m "$ALIAS" '{model: $m, max_completion_tokens: 16,
  messages: [{role: "user", content: "Reply with one word."}]}')"
RESPONSE="$(mktemp)"
trap 'rm -f "$RESPONSE"' EXIT

echo "Sending $COUNT requests per session with \"model\": \"$ALIAS\" and a $HEADER header"
printf '%-9s %s\n' "Session" "Backend model of each request"
for s in "${SESSIONS[@]}"; do
  ROW=""
  FIRST=""
  SAME="stays"
  for i in $(seq 1 "$COUNT"); do
    if [ "$s" = "none" ]; then ARGS=(); else ARGS=(-H "$HEADER: $s"); fi
    CODE="$(curl -sS -o "$RESPONSE" -w '%{http_code}' "$URL" ${ARGS[@]+"${ARGS[@]}"} \
      -H "Authorization: Bearer $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" -d "$BODY")"
    if [ "$CODE" = "200" ]; then
      SERVED="$(jq -r '.model // "unknown" | sub("-[0-9]{4}-[0-9]{2}-[0-9]{2}$"; "")' "$RESPONSE")"
    else
      SERVED="HTTP-$CODE"
    fi
    [ -z "$FIRST" ] && FIRST="$SERVED"
    [ "$SERVED" != "$FIRST" ] && SAME="moves"
    ROW+="$(printf '%-13s' "$SERVED")"
    sleep "$PAUSE"
  done
  printf '%-9s %s %s\n' "$s" "$ROW" "$SAME"
done
