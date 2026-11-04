#!/usr/bin/env bash
# Sends a small mix of chat completions through AI Gateway so the Monitoring dashboard has data to show.
# Every request carries an x-correlation-id header. The last request asks for an alias that doesn't exist,
# so you also get one failed request to find in Monitoring › Traces.
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   export AI_GATEWAY_API_KEY="..."      # never commit this value
#   ./generate-traffic.sh <model-name> [requests]
set -euo pipefail

MODEL="${1:?Pass the callable model alias as the first argument}"
REQUESTS="${2:-10}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a runtime key from Access > Keys}"

URL="${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions"
RUN_ID="lab13-$(date +%s)"
PROMPTS=(
  "Summarize what an AI gateway does in one sentence."
  "List three reasons to apply policies in front of model calls."
  "Write a haiku about observability."
  "Explain an OpenTelemetry trace to a new developer in two sentences."
)

send() { # <model> <prompt> <correlation-id>
  local body
  body=$(printf '{"model":"%s","messages":[{"role":"user","content":"%s"}]}' "$1" "$2")
  curl -sS -o /dev/null -w '%{http_code}' "$URL" \
    -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
    -H "x-correlation-id: $3" -d "$body"
}

printf '%-8s %-24s %-7s %s\n' "Request" "Model" "Status" "x-correlation-id"
for i in $(seq 1 "$REQUESTS"); do
  prompt="${PROMPTS[$(( (i - 1) % ${#PROMPTS[@]} ))]}"
  status=$(send "$MODEL" "$prompt" "$RUN_ID-$i")
  printf '%-8s %-24s %-7s %s\n' "$i" "$MODEL" "$status" "$RUN_ID-$i"
  sleep 1
done

status=$(send "does-not-exist" "This alias isn't published." "$RUN_ID-error")
printf '%-8s %-24s %-7s %s\n' "error" "does-not-exist" "$status" "$RUN_ID-error"
