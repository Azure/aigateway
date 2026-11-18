#!/usr/bin/env bash
# Sends a burst of chat requests to one alias and prints, for each one, the HTTP status, the model that served it
# (the x-ms-served-model response header), and Retry-After. Then it counts the outcomes.
# Usage: ./infra/burst.sh [alias] [requests] [pause-seconds]
# Needs AI_GATEWAY_URL and AI_GATEWAY_API_KEY in the environment, plus curl.
set -euo pipefail

ALIAS="${1:-chat-failover}"
COUNT="${2:-20}"
PAUSE="${3:-1}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a gateway runtime API key}"

URL="${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions"
BODY="{\"model\":\"$ALIAS\",\"max_completion_tokens\":16,\"messages\":[{\"role\":\"user\",\"content\":\"Reply with one word.\"}]}"

# Print the value of one response header, or nothing when the response doesn't have it
header() { printf '%s\n' "$HEADERS" | awk -F': ' -v n="$1" 'tolower($1)==n {gsub("\r","",$2); print $2}'; }

echo "Sending $COUNT requests with \"model\": \"$ALIAS\""
printf '%-4s %-6s %-7s %-26s %s\n' "#" "Time" "Status" "Served by" "Retry-After"
START="$(date +%s)"
TALLY=""
for i in $(seq 1 "$COUNT"); do
  HEADERS="$(curl -sS -D - -o /dev/null "$URL" -H "Authorization: Bearer $AI_GATEWAY_API_KEY" \
    -H "Content-Type: application/json" -d "$BODY" || true)"
  CODE="$(printf '%s\n' "$HEADERS" | awk 'toupper($1) ~ /^HTTP/ {c=$2} END {print c}')"
  SERVED="$(header x-ms-served-model)"
  RETRY="$(header retry-after)"
  printf '%-4s %-6s %-7s %-26s %s\n' "$i" "$(( $(date +%s) - START ))s" "${CODE:-none}" "${SERVED:--}" "${RETRY:--}"
  if [ "$CODE" = "200" ]; then TALLY+="200 ${SERVED:-unknown}"$'\n'; else TALLY+="${CODE:-none}"$'\n'; fi
  sleep "$PAUSE"
done

echo
echo "Outcomes:"
printf '%s' "$TALLY" | sort | uniq -c | sort -rn
