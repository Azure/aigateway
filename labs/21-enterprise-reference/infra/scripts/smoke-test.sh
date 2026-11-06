#!/usr/bin/env bash
# Post-deployment smoke test for the enterprise reference gateway. It proves the two runtime paths work end to end:
#   1. Model: a chat completion through the alias with an app's runtime API key (gateway -> managed identity -> Foundry).
#   2. Tools: the MCP handshake and tools/list on the federated Microsoft Learn MCP server.
# It reads the gateway host name and the key with the aigateway CLI extension, and it never prints the key.
# In GitHub Actions the key is also masked in the log.
#
# Usage:
#   export RG="<gateway-resource-group>" GATEWAY="<gateway-name>"
#   ./smoke-test.sh [alias] [api-key-name] [mcp-server]
#   ./smoke-test.sh chat web-chat learn
#
# Exits 0 when both checks pass, 1 otherwise. Requires Azure CLI with the aigateway extension, curl, and jq.
set -euo pipefail

ALIAS="${1:-chat}"
KEY_NAME="${2:-web-chat}"
SERVER="${3:-learn}"
: "${RG:?Set RG to the gateway resource group}"
: "${GATEWAY:?Set GATEWAY to the gateway name}"
command -v jq >/dev/null || { echo "This script needs jq." >&2; exit 1; }
az extension show --name aigateway -o none 2>/dev/null \
  || { echo "This script needs the aigateway CLI extension: curl -fsSL https://aka.ms/aigateway-cli-install | sh" >&2; exit 1; }

GATEWAY_HOST="$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.frontend.defaultHostname -o tsv)"
if [ -z "$GATEWAY_HOST" ]; then echo "Couldn't read the host name of gateway '$GATEWAY'." >&2; exit 1; fi
GATEWAY_URL="https://$GATEWAY_HOST"
API_KEY="$(az aigateway api-key list-secrets -g "$RG" --gateway-name "$GATEWAY" -n "$KEY_NAME" \
  --query primaryKey -o tsv)"
if [ -z "$API_KEY" ]; then echo "Couldn't read the secret of API key '$KEY_NAME'." >&2; exit 1; fi
if [ "${GITHUB_ACTIONS:-}" = "true" ]; then echo "::add-mask::$API_KEY"; fi

echo "Gateway: $GATEWAY_URL"

# 1. Model route. New role assignments and new models can take a few minutes to start answering, so retry.
CHAT_URL="${GATEWAY_URL%/}/default/models/openai/v1/chat/completions"
CHAT_BODY="$(jq -cn --arg model "$ALIAS" \
  '{model: $model, messages: [{role: "user", content: "Reply with exactly one word: ok"}], max_completion_tokens: 128}')"
STATUS="" BODY=""
for attempt in $(seq 1 15); do
  RAW="$(curl -sS --max-time 60 -w $'\n%{http_code}' -X POST "$CHAT_URL" \
    -H "api-key: $API_KEY" -H "Content-Type: application/json" --data "$CHAT_BODY" || true)"
  STATUS="${RAW##*$'\n'}"
  BODY="${RAW%$'\n'*}"
  case "$STATUS" in 2??) break ;; esac
  if [ "$attempt" -lt 15 ]; then
    echo "Waiting for the model route (attempt $attempt, HTTP ${STATUS:-unavailable})..."
    sleep 4
  fi
done
case "$STATUS" in
  2??)
    printf 'Model  : HTTP %s, model=%s, reply=%s, total_tokens=%s\n' "$STATUS" \
      "$(printf '%s' "$BODY" | jq -r '.model // "?"')" \
      "$(printf '%s' "$BODY" | jq -r '.choices[0].message.content // "" | gsub("\\s+"; " ")')" \
      "$(printf '%s' "$BODY" | jq -r '.usage.total_tokens // "?"')" ;;
  *)
    echo "Model  : FAILED with HTTP ${STATUS:-unavailable}" >&2
    printf '%s\n' "$BODY" | jq . 2>/dev/null >&2 || printf '%s\n' "$BODY" >&2
    exit 1 ;;
esac

# 2. MCP route: initialize -> notifications/initialized -> tools/list (Streamable HTTP).
ENDPOINT="${GATEWAY_URL%/}/default/toolservers/${SERVER}/mcp"
HEADERS=(-H "api-key: $API_KEY" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream")
SESSION_ID=""

# post <json>: sends one JSON-RPC message and sets STATUS, BODY, and SESSION_ID (when returned).
post() {
  local raw head sid
  raw="$(curl -sS --max-time 60 -D - "$ENDPOINT" "${HEADERS[@]}" --data "$1" | tr -d '\r')"
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

# require_success <step>: prints the gateway's answer and stops when the HTTP status isn't 2xx.
require_success() {
  case "$STATUS" in
    2??) ;;
    *)
      echo "Tools  : FAILED at $1 with HTTP ${STATUS:-unavailable}" >&2
      printf '%s\n' "$BODY" | jq . 2>/dev/null >&2 || printf '%s\n' "$BODY" >&2
      exit 1 ;;
  esac
}

post '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"aigateway-smoke-test","version":"1.0"}}}'
require_success "initialize"
PROTOCOL="$(response 1 | jq -r '.result.protocolVersion // empty')"
if [ -z "$PROTOCOL" ]; then echo "Tools  : FAILED, initialize returned no result" >&2; printf '%s\n' "$BODY" >&2; exit 1; fi
HEADERS+=(-H "MCP-Protocol-Version: $PROTOCOL")
if [ -n "$SESSION_ID" ]; then HEADERS+=(-H "Mcp-Session-Id: $SESSION_ID"); fi

post '{"jsonrpc":"2.0","method":"notifications/initialized"}'
require_success "notifications/initialized"

post '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
require_success "tools/list"
LIST="$(response 2)"
if [ -z "$LIST" ] || [ "$(printf '%s' "$LIST" | jq 'has("error")')" = "true" ]; then
  echo "Tools  : FAILED, tools/list returned an error" >&2; printf '%s\n' "${LIST:-$BODY}" >&2; exit 1
fi
COUNT="$(printf '%s' "$LIST" | jq '.result.tools | length')"
if [ "$COUNT" -lt 1 ]; then echo "Tools  : FAILED, tools/list returned no tools" >&2; exit 1; fi
echo "Tools  : HTTP $STATUS, $COUNT tools on $SERVER"
printf '%s' "$LIST" | jq -r '.result.tools[].name | "         " + .'

echo "Smoke test passed."
