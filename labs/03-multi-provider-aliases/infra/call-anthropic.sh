#!/usr/bin/env bash
# Calls a model through AI Gateway with the native Anthropic Messages API and prints the HTTP status,
# the backend model that answered, and the reply. The gateway passes the request through unchanged,
# so the body and the response use Anthropic's format.
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   export AI_GATEWAY_API_KEY="..."      # your gateway runtime key, never the provider key; never commit it
#   ./call-anthropic.sh <alias> ["Your prompt"]
# Requires curl and jq.
set -euo pipefail

ALIAS="${1:?Pass the callable alias as the first argument}"
PROMPT="${2:-In one sentence, what is an AI gateway?}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a runtime key from Access > Keys}"

URL="${AI_GATEWAY_URL%/}/default/models/anthropic/v1/messages"
BODY="$(jq -cn --arg model "$ALIAS" --arg prompt "$PROMPT" \
  '{model: $model, max_tokens: 1024, messages: [{role: "user", content: $prompt}]}')"

RESPONSE="$(curl -sS -w '\n%{http_code}' "$URL" \
  -H "api-key: $AI_GATEWAY_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d "$BODY")"
STATUS="${RESPONSE##*$'\n'}"
CONTENT="${RESPONSE%$'\n'*}"

echo "Alias:   $ALIAS"
echo "Status:  $STATUS"
if [ "$STATUS" = "200" ]; then
  echo "Model:   $(jq -r '.model' <<<"$CONTENT")"
  echo "Reply:   $(jq -r '[.content[]? | select(.type == "text") | .text] | join("")' <<<"$CONTENT")"
else
  echo "Body:    $CONTENT"
  exit 1
fi
