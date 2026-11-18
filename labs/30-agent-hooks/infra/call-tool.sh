#!/usr/bin/env bash
# Calls one tool on an AI Gateway MCP server with the MCP Streamable HTTP handshake
# (initialize -> notifications/initialized -> tools/call), and prints whether the result came back or the gateway's
# denial: the JSON-RPC error, or isError with the denial details in _meta.
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   export AI_GATEWAY_API_KEY="<runtime key>"            # Access > API keys; never paste it into a file
#   ./call-tool.sh <tool-name> '<arguments as JSON>' [server-name]
#
# Example:
#   ./call-tool.sh learn_microsoft_docs_search '{"query": "What is Azure Functions?"}'
# Requires curl and jq.
set -euo pipefail

TOOL="${1:?Pass the tool name, for example learn_microsoft_docs_search}"
ARGS="${2:-}"
[ -n "$ARGS" ] || ARGS='{}'
SERVER="${3:-learn}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a runtime key from Access > API keys}"
command -v jq >/dev/null || { echo "This script needs jq." >&2; exit 1; }
printf '%s' "$ARGS" | jq -e 'type == "object"' >/dev/null || { echo "The arguments must be a JSON object." >&2; exit 1; }
ENDPOINT="${AI_GATEWAY_URL%/}/default/toolservers/${SERVER}/mcp"
HEADERS=(-H "Authorization: Bearer $AI_GATEWAY_API_KEY" -H "Content-Type: application/json"
  -H "Accept: application/json, text/event-stream")
STATUS="" BODY="" SESSION_ID=""

# post <json>: sends one JSON-RPC message and sets STATUS and BODY (and SESSION_ID when the server returns one).
post() {
  local raw head sid
  raw="$(curl -sS --max-time 120 -D - "$ENDPOINT" "${HEADERS[@]}" --data "$1" | tr -d '\r')"
  if [[ "$raw" == *$'\n\n'* ]]; then head="${raw%%$'\n\n'*}"; BODY="${raw#*$'\n\n'}"; else head="$raw"; BODY=""; fi
  STATUS="$(printf '%s\n' "$head" | awk 'toupper($1) ~ /^HTTP/ {code=$2} END {print code}')"
  sid="$(printf '%s\n' "$head" | awk -F': ' 'tolower($1)=="mcp-session-id" {print $2}')"
  if [ -n "$sid" ]; then SESSION_ID="$sid"; fi
}

# response <id>: prints the JSON-RPC response with that id. The body can be JSON or server-sent events.
response() {
  if printf '%s\n' "$BODY" | grep -q '^data:'; then
    printf '%s\n' "$BODY" | sed -n 's/^data:[[:space:]]*//p'
  else
    printf '%s\n' "$BODY"
  fi | jq -c --argjson id "$1" 'select(type == "object" and .id == $id)' 2>/dev/null || true
}

# require_success <step>: stops with the gateway's answer when the HTTP status isn't 2xx.
require_success() {
  case "$STATUS" in
    2??) ;;
    *) echo "$1 failed with HTTP ${STATUS:-no response}:" >&2; printf '%s\n' "$BODY" >&2; exit 1 ;;
  esac
}

post '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"aigateway-labs","version":"1.0"}}}'
require_success "initialize"
PROTOCOL="$(response 1 | jq -r '.result.protocolVersion // empty')"
if [ -z "$PROTOCOL" ]; then echo "initialize returned no result:" >&2; printf '%s\n' "$BODY" >&2; exit 1; fi
HEADERS+=(-H "MCP-Protocol-Version: $PROTOCOL")
if [ -n "$SESSION_ID" ]; then HEADERS+=(-H "Mcp-Session-Id: $SESSION_ID"); fi

post '{"jsonrpc":"2.0","method":"notifications/initialized"}'
require_success "notifications/initialized"

echo "tools/call $TOOL $(printf '%s' "$ARGS" | jq -c .)"
post "$(jq -cn --arg name "$TOOL" --argjson args "$ARGS" \
  '{jsonrpc:"2.0",id:2,method:"tools/call",params:{name:$name,arguments:$args}}')"
require_success "tools/call"
CALL="$(response 2)"
if [ -z "$CALL" ]; then echo "tools/call returned no JSON-RPC response:" >&2; printf '%s\n' "$BODY" >&2; exit 1; fi

echo "HTTP status: $STATUS"
if [ "$(printf '%s' "$CALL" | jq 'has("error")')" = "true" ]; then
  echo "JSON-RPC error:"; printf '%s' "$CALL" | jq '.error'
elif [ "$(printf '%s' "$CALL" | jq '.result.isError == true')" = "true" ]; then
  echo "isError: true"
  printf '%s' "$CALL" | jq -r '[.result.content[]? | select(.type == "text") | .text] | join("\n")'
  printf '%s' "$CALL" | jq '.result._meta // empty'
else
  echo "isError: false (the result was returned)"
  printf '%s' "$CALL" | jq -r '[.result.content[]? | select(.type == "text") | .text] | join("\n") | .[0:300]'
  echo "..."
fi
