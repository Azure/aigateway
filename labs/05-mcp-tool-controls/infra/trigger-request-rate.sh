#!/usr/bin/env bash
# Sends a burst of MCP requests to an AI Gateway MCP server and prints the HTTP status and
# Retry-After header of each one so you can watch a request rate limit engage.
# Every HTTP request counts as a call, including the two handshake messages.
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   export AI_GATEWAY_API_KEY="..."      # never commit this value
#   ./trigger-request-rate.sh [server-name] [tools/list requests]
#
# Set AI_GATEWAY_MCP_ENDPOINT to use a full MCP endpoint URL instead of building it from AI_GATEWAY_URL.
# Requires curl and jq.
set -euo pipefail

SERVER="${1:-learn}"
REQUESTS="${2:-8}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a runtime key from Access > Keys}"
if [ -z "${AI_GATEWAY_MCP_ENDPOINT:-}" ]; then
  : "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
  AI_GATEWAY_MCP_ENDPOINT="${AI_GATEWAY_URL%/}/default/toolservers/${SERVER}/mcp"
fi
command -v jq >/dev/null || { echo "This script needs jq." >&2; exit 1; }

HEADERS=(-H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json"
  -H "Accept: application/json, text/event-stream")
COUNT=0 STATUS="" BODY="" SESSION_ID=""

# send <label> <json>: sends one JSON-RPC message and prints one result row.
send() {
  local raw head retry sid
  raw="$(curl -sS --max-time 60 -D - "$AI_GATEWAY_MCP_ENDPOINT" "${HEADERS[@]}" --data "$2" | tr -d '\r')"
  if [[ "$raw" == *$'\n\n'* ]]; then head="${raw%%$'\n\n'*}"; BODY="${raw#*$'\n\n'}"; else head="$raw"; BODY=""; fi
  STATUS="$(printf '%s\n' "$head" | awk 'toupper($1) ~ /^HTTP/ {code=$2} END {print code}')"
  retry="$(printf '%s\n' "$head" | awk -F': ' 'tolower($1)=="retry-after" {print $2}')"
  sid="$(printf '%s\n' "$head" | awk -F': ' 'tolower($1)=="mcp-session-id" {print $2}')"
  if [ -n "$sid" ]; then SESSION_ID="$sid"; fi
  COUNT=$((COUNT + 1))
  printf '%-8s %-27s %-7s %s\n' "$COUNT" "$1" "${STATUS:-none}" "${retry:--}"
}

echo "MCP endpoint: $AI_GATEWAY_MCP_ENDPOINT"
echo
printf '%-8s %-27s %-7s %s\n' "Request" "Method" "Status" "Retry-After"

send "initialize" '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"aigateway-labs","version":"1.0"}}}'
PROTOCOL="$(if [[ "$BODY" == data:* || "$BODY" == *$'\n'data:* ]]; then printf '%s\n' "$BODY" | sed -n 's/^data:[[:space:]]*//p'; else printf '%s\n' "$BODY"; fi |
  jq -r 'select(type == "object") | .result.protocolVersion // empty' 2>/dev/null | head -n 1 || true)"
if [ -n "$PROTOCOL" ]; then HEADERS+=(-H "MCP-Protocol-Version: $PROTOCOL"); fi
if [ -n "$SESSION_ID" ]; then HEADERS+=(-H "Mcp-Session-Id: $SESSION_ID"); fi

send "notifications/initialized" '{"jsonrpc":"2.0","method":"notifications/initialized"}'

for i in $(seq 1 "$REQUESTS"); do
  send "tools/list" "{\"jsonrpc\":\"2.0\",\"id\":$((i + 1)),\"method\":\"tools/list\",\"params\":{}}"
done

if [ "$STATUS" = "429" ] && [ -n "$BODY" ]; then
  echo
  echo "Last response body:"
  printf '%s\n' "$BODY"
fi
