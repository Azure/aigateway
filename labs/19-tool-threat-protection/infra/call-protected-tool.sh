#!/usr/bin/env bash
# Calls one tool on an AI Gateway MCP server that has Agent 365 tool threat protection, using the MCP
# Streamable HTTP handshake (initialize -> notifications/initialized -> tools/list -> tools/call).
# Prints whether the tool result came back, or the denial code and correlation ID the gateway returned.
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   ./call-protected-tool.sh token [server-name] [query]   # delegated Entra token for the signed-in az user
#   ./call-protected-tool.sh key   [server-name] [query]   # runtime key in AI_GATEWAY_API_KEY (no bearer token)
#
# token mode uses AI_GATEWAY_TOKEN when set, otherwise it runs
#   az account get-access-token --resource https://azure-api.net/aigateway
# The script calls the Learn docs search tool (or the first tool whose name contains "search") unless you set
# TOOL_NAME, and sends the query as {"query": "..."}. Use a benign query. Requires curl and jq.
set -euo pipefail

AUTH="${1:?Pass token or key as the first argument}"
SERVER="${2:-learn}"
QUERY="${3:-What is Azure API Management?}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
command -v jq >/dev/null || { echo "This script needs jq." >&2; exit 1; }
ENDPOINT="${AI_GATEWAY_URL%/}/default/toolservers/${SERVER}/mcp"

case "$AUTH" in
  token)
    TOKEN="${AI_GATEWAY_TOKEN:-$(az account get-access-token --resource https://azure-api.net/aigateway --query accessToken -o tsv)}"
    # Delegated (user) tokens carry an scp claim. App-only tokens carry roles instead and can't be used for evaluation.
    payload="$(printf '%s' "$TOKEN" | cut -d. -f2 | tr '_-' '/+')"
    while [ $(( ${#payload} % 4 )) -ne 0 ]; do payload="${payload}="; done
    scp="$(printf '%s' "$payload" | jq -Rr '@base64d | fromjson | .scp // empty' 2>/dev/null || true)"
    if [ -n "$scp" ]; then
      echo "Delegated token for the signed-in user (scp: $scp)"
    else
      echo "Warning: the token has no scp claim, so it isn't a delegated user token." >&2
    fi
    HEADERS=(-H "Authorization: Bearer $TOKEN") ;;
  key)
    : "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a runtime key from Access > Keys}"
    HEADERS=(-H "api-key: $AI_GATEWAY_API_KEY") ;;
  *)
    echo "The first argument must be token or key." >&2; exit 1 ;;
esac
HEADERS+=(-H "Content-Type: application/json" -H "Accept: application/json, text/event-stream")
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
echo "tools/list: HTTP $STATUS, $(printf '%s' "$LIST" | jq '.result.tools | length') tools (discovery isn't evaluated)"

TOOL="${TOOL_NAME:-$(printf '%s' "$LIST" | jq -r '[.result.tools[].name] |
  ([.[] | select(test("docs_search"; "i"))] + [.[] | select(test("search"; "i"))])[0] // empty')}"
if [ -z "$TOOL" ]; then echo "No tool name contains 'search'. Set TOOL_NAME to the tool to call." >&2; exit 1; fi

echo "tools/call: $TOOL with query: $QUERY"
post "$(jq -cn --arg name "$TOOL" --arg query "$QUERY" \
  '{jsonrpc:"2.0",id:3,method:"tools/call",params:{name:$name,arguments:{query:$query}}}')"
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
