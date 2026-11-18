#!/usr/bin/env bash
# Calls the obo-demo MCP server of lab 33 through Azure AI Gateway as the signed-in az user, and checks each link of
# the on-behalf-of chain:
#   1. A call without a token gets 401 from the gateway.
#   2. The MCP handshake (initialize -> notifications/initialized -> tools/list) with your token for the gateway.
#   3. demo_whoami returns the claims of the token that the backend received: the same user (oid), issued for the
#      backend's API (aud), and requested by the token exchange app (azp).
#   4. When BACKEND_URL is set, your gateway token sent straight to the backend gets 401: only the exchanged token works.
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   export BACKEND_URL="<backend-url>"   # optional, enables check 4
#   ./call-obo-tool.sh [server-name]       # default: obo-demo
#
# The script uses AI_GATEWAY_TOKEN when set, otherwise it runs
#   az account get-access-token --scope https://ai.gateway.azure.com/Data.All
# It never prints a token. Requires curl and jq.
set -euo pipefail

SERVER="${1:-obo-demo}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
command -v jq >/dev/null || { echo "This script needs jq." >&2; exit 1; }
ENDPOINT="${AI_GATEWAY_URL%/}/default/toolservers/${SERVER}/mcp"
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"aigateway-labs","version":"1.0"}}}'

# claims <jwt>: prints the decoded payload of a token.
claims() {
  local payload
  payload="$(printf '%s' "$1" | cut -d. -f2 | tr '_-' '/+')"
  while [ $(( ${#payload} % 4 )) -ne 0 ]; do payload="${payload}="; done
  printf '%s' "$payload" | jq -Rr '@base64d | fromjson' 2>/dev/null || echo '{}'
}

echo "MCP endpoint: $ENDPOINT"

# 1. Without a token.
ANON="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 60 "$ENDPOINT" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" --data "$INIT")"
if [ "$ANON" = "401" ]; then echo "1. Without a token: HTTP 401, as expected"
else echo "1. Without a token: HTTP $ANON (expected 401)" >&2; fi

TOKEN="${AI_GATEWAY_TOKEN:-$(az account get-access-token --scope https://ai.gateway.azure.com/Data.All --query accessToken -o tsv)}"
CALLER="$(claims "$TOKEN")"
CALLER_OID="$(printf '%s' "$CALLER" | jq -r '.oid // empty')"
echo "   Your token for the gateway: aud $(printf '%s' "$CALLER" | jq -r '.aud') scp $(printf '%s' "$CALLER" | jq -r '.scp // "none"') oid $CALLER_OID"

HEADERS=(-H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream")
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

# 2. The handshake.
post "$INIT"
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
echo "2. Handshake: MCP version $PROTOCOL, tools: $(printf '%s' "$LIST" | jq -r '[.result.tools[].name] | join(", ")')"

# 3. whoami.
TOOL="$(printf '%s' "$LIST" | jq -r '[.result.tools[].name | select(endswith("whoami"))][0] // empty')"
if [ -z "$TOOL" ]; then echo "No tool name ends with whoami." >&2; exit 1; fi
post "$(jq -cn --arg name "$TOOL" '{jsonrpc:"2.0",id:3,method:"tools/call",params:{name:$name,arguments:{}}}')"
require_success "tools/call"
CALL="$(response 3)"
if [ -z "$CALL" ] || [ "$(printf '%s' "$CALL" | jq 'has("error") or .result.isError == true')" = "true" ]; then
  echo "tools/call $TOOL failed:" >&2; printf '%s\n' "${CALL:-$BODY}" >&2; exit 1
fi
WHO="$(printf '%s' "$CALL" | jq -c '.result.structuredContent // (.result.content[0].text | fromjson)')"
echo "3. $TOOL: the backend received this token:"
printf '%s' "$WHO" | jq '{name, username, object_id, audience, client_app_id, scopes}'
if [ "$(printf '%s' "$WHO" | jq -r '.object_id')" = "$CALLER_OID" ]; then
  echo "   Same user as your token for the gateway, different audience: the gateway exchanged it on your behalf"
else
  echo "   The backend saw a different user than your token's oid ($CALLER_OID)" >&2
fi

# 4. Your gateway token, straight to the backend.
if [ -n "${BACKEND_URL:-}" ]; then
  DIRECT="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 60 "$BACKEND_URL" -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" --data "$INIT")"
  if [ "$DIRECT" = "401" ]; then echo "4. Your gateway token sent straight to the backend: HTTP 401, as expected"
  else echo "4. Your gateway token sent straight to the backend: HTTP $DIRECT (expected 401)" >&2; fi
fi
