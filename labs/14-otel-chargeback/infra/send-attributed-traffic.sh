#!/usr/bin/env bash
# Sends chat completions through AI Gateway as two kinds of caller: a runtime API key and your Microsoft Entra
# identity. Telemetry then has an API key ID for the first batch and token claims (tid, oid, appid or azp) for the
# second, so you can attribute both in a chargeback report.
#
# The Entra calls need the AI Gateway Models User role (or AI Gateway User) on the gateway or the model.
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   export AI_GATEWAY_API_KEY="..."      # never commit this value
#   az login
#   ./send-attributed-traffic.sh <model-name> [requests-per-caller]
set -euo pipefail

MODEL="${1:?Pass the callable model alias as the first argument}"
REQUESTS="${2:-5}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a runtime key from Access > Keys}"

URL="${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions"
RUN_ID="lab14-$(date +%s)"
TOKEN="$(az account get-access-token --resource https://azure-api.net/aigateway --query accessToken -o tsv)"
BODY=$(printf '{"model":"%s","messages":[{"role":"user","content":"In one sentence, what is a chargeback report?"}]}' "$MODEL")

send() { # <auth-header> <correlation-id>
  curl -sS -o /dev/null -w '%{http_code}' "$URL" \
    -H "$1" -H "Content-Type: application/json" -H "x-correlation-id: $2" -d "$BODY"
}

printf '%-10s %-8s %-7s %s\n' "Caller" "Request" "Status" "x-correlation-id"
for i in $(seq 1 "$REQUESTS"); do
  status=$(send "api-key: $AI_GATEWAY_API_KEY" "$RUN_ID-key-$i")
  printf '%-10s %-8s %-7s %s\n' "api-key" "$i" "$status" "$RUN_ID-key-$i"
  status=$(send "Authorization: Bearer $TOKEN" "$RUN_ID-entra-$i")
  printf '%-10s %-8s %-7s %s\n' "entra" "$i" "$status" "$RUN_ID-entra-$i"
  sleep 1
done
