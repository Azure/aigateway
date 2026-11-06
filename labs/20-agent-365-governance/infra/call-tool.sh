#!/usr/bin/env bash
# Connects to an AI Gateway MCP server with the MCP Streamable HTTP handshake
# (initialize -> notifications/initialized -> tools/list), prints the published tools, and optionally calls one
# tool. Unlike a plain client, it prints the gateway's answer when a server or tool is blocked, so you can see
# how Agent 365 and gateway controls reach the caller.
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   export AI_GATEWAY_API_KEY="..."      # never commit this value
#   ./call-tool.sh [server-name] [tool-name] [arguments-json]
#
# Examples:
#   ./call-tool.sh learn
#   ./call-tool.sh learn learn_microsoft_docs_search '{"query":"What is Microsoft Agent 365?"}'
#   ./call-tool.sh learn learn_microsoft_docs_fetch '{"url":"https://learn.microsoft.com/azure/api-management/agent-365"}'
#
# Requires curl and jq.
set -euo pipefail

SERVER="${1:-learn}"
TOOL="${2:-}"
ARGS="${3:-}"
if [ -z "$ARGS" ]; then ARGS="{}"; fi
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a runtime key from Access > Keys}"
command -v jq >/dev/null || { echo "This script needs jq." >&2; exit 1; }
printf '%s' "$ARGS" | jq -e 'type == "object"' >/dev/null || { echo "arguments-json must be a JSON object." >&2; exit 1; }
ENDPOINT="${AI_GATEWAY_URL%/}/default/toolservers/${SERVER}/mcp"

HEADERS=(-H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json"
  -H "Accept: application/json, text/event-stream")
STATUS="" BODY="" SESSION_ID="" CORRELATION_ID=""

# post <json>: sends one JSON-RPC message and sets STATUS, BODY, CORRELATION_ID, and SESSION_ID (when returned).
post() {
  local raw head sid
  raw="$(curl -sS --max-time 60 -D - "$ENDPOINT" "${HEADERS[@]}" --data "$1" | tr -d '\r')"
  if [[ "$raw" == *$'\n\n'* ]]; then head="${raw%%$'\n\n'*}"; BODY="${raw#*$'\n\n'}"; else head="$raw"; BODY=""; fi
  STATUS="$(printf '%s\n' "$head" | awk 'toupper($1) ~ /^HTTP/ {code=$2} END {print code}')"
  CORRELATION_ID="$(printf '%s\n' "$head" | awk -F': ' 'tolower($1)=="x-correlation-id" {print $2}')"
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

# require_success <step>: prints the gateway's answer and stops when the HTTP status isn't 2xx.
require_success() {
  case "$STATUS" in
    2??) ;;
    *)
      echo "$1: HTTP ${STATUS:-no response}${CORRELATION_ID:+ (x-correlation-id: $CORRELATION_ID)}"
      printf '%s\n' "$BODY" | jq . 2>/dev/null || printf '%s\n' "$BODY"
      exit 1 ;;
  esac
}

echo "MCP endpoint: $ENDPOINT"

post '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"aigateway-labs","version":"1.0"}}}'
require_success "initialize"
PROTOCOL="$(response 1 | jq -r '.result.protocolVersion // empty')"
if [ -z "$PROTOCOL" ]; then echo "initialize returned no result:" >&2; printf '%s\n' "$BODY" >&2; exit 1; fi
HEADERS+=(-H "MCP-Protocol-Version: $PROTOCOL")
if [ -n "$SESSION_ID" ]; then HEADERS+=(-H "Mcp-Session-Id: $SESSION_ID"); fi

post '{"jsonrpc":"2.0","method":"notifications/initialized"}'
require_success "notifications/initialized"

post '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
require_success "tools/list"
LIST="$(response 2)"
if [ -z "$LIST" ] || [ "$(printf '%s' "$LIST" | jq 'has("error")')" = "true" ]; then
  echo "tools/list returned an error:" >&2; printf '%s\n' "${LIST:-$BODY}" >&2; exit 1
fi
echo "tools/list: HTTP $STATUS"
printf '%s' "$LIST" | jq -r '.result.tools[].name | "  " + .'

if [ -z "$TOOL" ]; then exit 0; fi

echo
echo "tools/call: $TOOL $ARGS"
post "$(jq -cn --arg name "$TOOL" --argjson args "$ARGS" \
  '{jsonrpc:"2.0",id:3,method:"tools/call",params:{name:$name,arguments:$args}}')"
require_success "tools/call"
CALL="$(response 3)"
if [ -z "$CALL" ]; then echo "tools/call returned no JSON-RPC response:" >&2; printf '%s\n' "$BODY" >&2; exit 1; fi

echo "HTTP status: $STATUS"
if [ "$(printf '%s' "$CALL" | jq 'has("error")')" = "true" ]; then
  echo "JSON-RPC error:"; printf '%s' "$CALL" | jq '.error'
elif [ "$(printf '%s' "$CALL" | jq '.result.isError == true')" = "true" ]; then
  echo "isError: true"
  printf '%s' "$CALL" | jq -r '.result._meta["com.microsoft.azure.ai.gateway/denial"] // {} |
    "Denial code: \(.code // "none")\nCorrelation ID: \(.correlationId // "none")"'
  printf '%s' "$CALL" | jq -r '[.result.content[]? | select(.type == "text") | .text] | join("\n")'
else
  echo "isError: false (the result was returned)"
  printf '%s' "$CALL" | jq -r '[.result.content[]? | select(.type == "text") | .text] | join("\n") | .[0:400]'
  echo "..."
fi
