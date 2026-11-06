#!/usr/bin/env bash
# Connects to an AI Gateway MCP server with the MCP Streamable HTTP handshake
# (initialize -> notifications/initialized -> tools/list), prints the published tools,
# and optionally calls one tool with a {"query": "..."} argument.
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   export AI_GATEWAY_API_KEY="..."      # never commit this value
#   ./list-tools.sh [server-name] [tool-name] [query]
#
# Examples:
#   ./list-tools.sh learn
#   ./list-tools.sh learn learn_microsoft_docs_search "What is AI Gateway?"
#
# Set AI_GATEWAY_MCP_ENDPOINT to use a full MCP endpoint URL instead of building it from AI_GATEWAY_URL.
# Requires curl and jq.
set -euo pipefail

SERVER="${1:-learn}"
TOOL="${2:-}"
QUERY="${3:-What is Azure AI Gateway?}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a runtime key from Access > Keys}"
if [ -z "${AI_GATEWAY_MCP_ENDPOINT:-}" ]; then
  : "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
  AI_GATEWAY_MCP_ENDPOINT="${AI_GATEWAY_URL%/}/default/toolservers/${SERVER}/mcp"
fi
command -v jq >/dev/null || { echo "This script needs jq." >&2; exit 1; }

HEADERS=(-H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json"
  -H "Accept: application/json, text/event-stream")
STATUS="" BODY="" SESSION_ID=""

# post <json>: sends one JSON-RPC message and sets STATUS and BODY (and SESSION_ID when the server returns one).
post() {
  local raw head sid
  raw="$(curl -sS --max-time 60 -D - "$AI_GATEWAY_MCP_ENDPOINT" "${HEADERS[@]}" --data "$1" | tr -d '\r')"
  if [[ "$raw" == *$'\n\n'* ]]; then head="${raw%%$'\n\n'*}"; BODY="${raw#*$'\n\n'}"; else head="$raw"; BODY=""; fi
  STATUS="$(printf '%s\n' "$head" | awk 'toupper($1) ~ /^HTTP/ {code=$2} END {print code}')"
  sid="$(printf '%s\n' "$head" | awk -F': ' 'tolower($1)=="mcp-session-id" {print $2}')"
  if [ -n "$sid" ]; then SESSION_ID="$sid"; fi
}

# response <id>: prints the JSON-RPC response with that id. The body can be JSON or server-sent events.
response() {
  if [[ "$BODY" == data:* || "$BODY" == *$'\n'data:* ]]; then
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

echo "MCP endpoint: $AI_GATEWAY_MCP_ENDPOINT"

post '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"aigateway-labs","version":"1.0"}}}'
require_success "initialize"
INIT="$(response 1)"
PROTOCOL="$(printf '%s' "$INIT" | jq -r '.result.protocolVersion // empty')"
if [ -z "$PROTOCOL" ]; then echo "initialize returned no result:" >&2; printf '%s\n' "$BODY" >&2; exit 1; fi
HEADERS+=(-H "MCP-Protocol-Version: $PROTOCOL")
if [ -n "$SESSION_ID" ]; then HEADERS+=(-H "Mcp-Session-Id: $SESSION_ID"); fi
echo "Server: $(printf '%s' "$INIT" | jq -r '.result.serverInfo.name // "unknown"')  protocol: $PROTOCOL"

post '{"jsonrpc":"2.0","method":"notifications/initialized"}'
require_success "notifications/initialized"

post '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
require_success "tools/list"
LIST="$(response 2)"
if [ -z "$LIST" ] || [ "$(printf '%s' "$LIST" | jq 'has("error")')" = "true" ]; then
  echo "tools/list returned an error:" >&2; printf '%s\n' "${LIST:-$BODY}" >&2; exit 1
fi

echo
printf '%-45s %s\n' "Tool" "Description"
printf '%s' "$LIST" | jq -r '.result.tools[] | [.name, ((.description // "") | gsub("\\s+"; " ") | .[0:70])] | @tsv' |
  while IFS=$'\t' read -r name description; do printf '%-45s %s\n' "$name" "$description"; done
echo
echo "$(printf '%s' "$LIST" | jq '.result.tools | length') tools published"

if [ -n "$TOOL" ]; then
  echo
  echo "Calling $TOOL with query: $QUERY"
  post "$(jq -cn --arg name "$TOOL" --arg query "$QUERY" \
    '{jsonrpc:"2.0",id:3,method:"tools/call",params:{name:$name,arguments:{query:$query}}}')"
  require_success "tools/call"
  CALL="$(response 3)"
  if [ -z "$CALL" ] || [ "$(printf '%s' "$CALL" | jq 'has("error") or (.result.isError == true)')" = "true" ]; then
    echo "The tool call failed:" >&2; printf '%s\n' "${CALL:-$BODY}" >&2; exit 1
  fi
  printf '%s' "$CALL" | jq -r '[.result.content[]? | select(.type == "text") | .text] | join("\n") | .[0:600]'
  echo "..."
fi
