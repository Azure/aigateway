#!/usr/bin/env bash
# Sends a small mix of model and MCP calls through AI Gateway, so the Monitoring dashboard has data to show and
# failures to investigate:
#   - <requests> chat completions to your alias, which succeed
#   - a request for an alias that doesn't exist, which the gateway rejects with 404
#   - a message with an invalid role, which the model provider rejects with 400
#   - with a tool server name, such as learn from lab 04, a tools/call without the tool's required argument: the
#     response is HTTP 200, but the tool reports isError, so the trace marks the tool call as failed
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   export AI_GATEWAY_API_KEY="..."      # never commit this value
#   ./generate-traffic.sh <model-name> [requests] [tool-server]
set -euo pipefail

MODEL="${1:?Pass the callable model alias as the first argument}"
REQUESTS="${2:-10}"
TOOL_SERVER="${3:-}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a runtime key from Access > API keys}"

BASE="${AI_GATEWAY_URL%/}/default"
PROMPTS=(
  "Summarize what an AI gateway does in one sentence."
  "List three reasons to apply policies in front of model calls."
  "Write a haiku about observability."
  "Explain an OpenTelemetry trace to a new developer in two sentences."
)

chat() { # <model> <role> <prompt>: prints the HTTP status
  local body
  body=$(printf '{"model":"%s","messages":[{"role":"%s","content":"%s"}]}' "$1" "$2" "$3")
  curl -sS -o /dev/null -w '%{http_code}' "$BASE/models/openai/v1/chat/completions" \
    -H "Authorization: Bearer $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" -d "$body"
}

row() { printf '%-8s %-34s %-12s %s\n' "$@"; }

row "Request" "Target" "Status" "Expected"
for i in $(seq 1 "$REQUESTS"); do
  row "$i" "$MODEL" "$(chat "$MODEL" user "${PROMPTS[$(( (i - 1) % ${#PROMPTS[@]} ))]}")" "200"
  sleep 1
done
row "fail-1" "does-not-exist" "$(chat does-not-exist user "This alias isn't published.")" "404, unknown alias"
row "fail-2" "$MODEL" "$(chat "$MODEL" robot "robot isn't a valid role.")" "400, from the provider"

if [ -n "$TOOL_SERVER" ]; then
  # learn_microsoft_docs_fetch requires a url argument, so the tool runs and reports an error
  out=$(curl -sS -w '\n%{http_code}' "$BASE/toolservers/$TOOL_SERVER/mcp" \
    -H "Authorization: Bearer $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"learn_microsoft_docs_fetch","arguments":{}}}')
  status="${out##*$'\n'}"
  case "$out" in *'"isError":true'*) status="$status isError" ;; esac
  row "fail-3" "$TOOL_SERVER: learn_microsoft_docs_fetch" "$status" "200 isError, tool error"
fi
