#!/usr/bin/env bash
# Sends one small Chat Completions request through AI Gateway and reports whether the gateway accepted the
# runtime API key. Only the last four characters of the key are printed.
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   export AI_GATEWAY_MODEL="<model-name>"
#   export AI_GATEWAY_API_KEY="..."                 # the key to test; never commit it
#   ./check-key.sh ["label"]                        # test AI_GATEWAY_API_KEY
#   AI_GATEWAY_API_KEY="$OLD_KEY" ./check-key.sh "old value"
#   ./check-key.sh --no-key                         # send the request without an api-key header
# Requires curl.
set -euo pipefail

: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_MODEL:?Set AI_GATEWAY_MODEL to a callable model alias}"

URL="${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions"
BODY=$(printf '{"model":"%s","messages":[{"role":"user","content":"ping"}]}' "$AI_GATEWAY_MODEL")

if [[ "${1:-}" == "--no-key" ]]; then
  LABEL="no key"
  HINT="-"
  RESPONSE=$(curl -sS -w '\n%{http_code}' "$URL" \
    -H "Content-Type: application/json" -d "$BODY" || true)
else
  : "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to the runtime key to test}"
  LABEL="${1:-current key}"
  HINT="...${AI_GATEWAY_API_KEY: -4}"
  # The header is read from stdin so the key doesn't appear in the process list.
  RESPONSE=$(printf 'api-key: %s\n' "$AI_GATEWAY_API_KEY" | curl -sS -w '\n%{http_code}' "$URL" \
    -H @- -H "Content-Type: application/json" -d "$BODY" || true)
fi
STATUS="${RESPONSE##*$'\n'}"

case "$STATUS" in
  2??) RESULT="accepted" ;;
  401) RESULT="rejected: the key is missing, invalid, rotated, suspended, or deleted" ;;
  404) if [[ "$RESPONSE" == *model_not_found* ]]; then
         RESULT="not checked: the gateway doesn't know the alias in AI_GATEWAY_MODEL"
       else
         RESULT="key accepted, but the call failed: check AI_GATEWAY_MODEL and the gateway's policies"
       fi ;;
  000|"") RESULT="no response: check AI_GATEWAY_URL and your network"; STATUS="---" ;;
  *)   RESULT="key accepted, but the call failed: check AI_GATEWAY_MODEL and the gateway's policies" ;;
esac

printf '%-14s %-8s HTTP %s  %s\n' "$LABEL" "$HINT" "$STATUS" "$RESULT"
