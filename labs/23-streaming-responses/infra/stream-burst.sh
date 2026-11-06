#!/usr/bin/env bash
# Sends a burst of streamed chat completions through AI Gateway and prints, for each request, the status code,
# Retry-After, how many server-sent events arrived, and the tokens in the usage chunk if the stream had one.
# Run it without --usage and then with --usage to see that a token limit counts streamed tokens either way.
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   export AI_GATEWAY_API_KEY="..."      # never commit this value
#   ./stream-burst.sh [--usage] <model-name> [requests]
# Requires curl and jq.
set -euo pipefail

USAGE=false
if [[ "${1:-}" == "--usage" ]]; then USAGE=true; shift; fi
MODEL="${1:?Pass the callable model alias as the first argument}"
REQUESTS="${2:-8}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a runtime key from Access > Keys}"

URL="${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions"
# Each request asks for about 200 output tokens, the same prompt as lab 06.
BODY=$(jq -n --arg m "$MODEL" --argjson usage "$USAGE" '
  {model: $m, stream: true, max_completion_tokens: 250, reasoning_effort: "none",
   messages: [{role: "user", content: "Write a 150-word product update about an AI gateway that governs models and tools."}]}
  + (if $usage then {stream_options: {include_usage: true}} else {} end)')

headers=$(mktemp)
body=$(mktemp)
trap 'rm -f "$headers" "$body"' EXIT

printf '%-8s %-7s %-12s %-7s %s\n' "Request" "Status" "Retry-After" "Events" "Usage chunk"
for i in $(seq 1 "$REQUESTS"); do
  curl -sSN -D "$headers" -o "$body" "$URL" \
    -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" -d "$BODY"
  status=$(awk 'toupper($1) ~ /^HTTP/ {code=$2} END {print code}' "$headers")
  retry=$(awk -F': ' 'tolower($1)=="retry-after" {gsub("\r","",$2); print $2}' "$headers")
  if [[ "$status" == 200 ]]; then
    events=$(grep -c '^data: {' "$body" || true)
    usage=$(sed -n 's/^data: //p' "$body" | grep -v '^\[DONE\]$' \
      | jq -rs 'map(.usage // empty) | last | if . then "\(.total_tokens) tokens" else "none" end')
  else
    events="-"
    usage=$(jq -r '.message // .error.message // empty' "$body" 2>/dev/null || true)
  fi
  printf '%-8s %-7s %-12s %-7s %s\n' "$i" "$status" "${retry:--}" "$events" "${usage:--}"
done
