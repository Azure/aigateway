#!/usr/bin/env bash
# Sends a series of chat completions through AI Gateway and prints the status code, the error
# code, and the tokens used, so you can watch a cost limit block a caller with 403
# LlmCostQuotaExceeded. The last column lists any response header whose name mentions
# budget, cost, or remaining, so you can spot the remaining-budget header.
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   export AI_GATEWAY_API_KEY="..."      # never commit this value
#   ./trigger-cost-limit.sh <model-name> [requests]
set -euo pipefail

MODEL="${1:?Pass the callable model alias as the first argument}"
REQUESTS="${2:-10}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a runtime key from Access > Keys}"

URL="${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions"
# reasoning_effort none spends the budget on the reply instead of hidden reasoning, so token counts stay predictable.
BODY=$(cat <<EOF
{"model":"$MODEL","max_completion_tokens":250,"reasoning_effort":"none",
 "messages":[{"role":"user","content":"Write a 150-word note to a finance team explaining why per-app AI budgets help."}]}
EOF
)

printf '%-8s %-7s %-24s %-12s %s\n' "Request" "Status" "Error code" "Tokens used" "Budget headers"
for i in $(seq 1 "$REQUESTS"); do
  headers=$(mktemp)
  response=$(curl -sS -D "$headers" -o - "$URL" \
    -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" -d "$BODY")
  status=$(awk 'toupper($1) ~ /^HTTP/ {code=$2} END {print code}' "$headers")
  budget=$(awk -F': ' 'tolower($1) ~ /budget|cost|remaining/ {gsub("\r","",$2); printf "%s%s=%s", sep, $1, $2; sep="; "}' "$headers")
  used="" code=""
  if [ "$status" = "200" ]; then
    used=$(printf '%s' "$response" | sed -n 's/.*"total_tokens":[[:space:]]*\([0-9]*\).*/\1/p')
  else
    code=$(printf '%s' "$response" | sed -n 's/.*"code":[[:space:]]*"\([^"]*\)".*/\1/p' | awk 'NR==1')
  fi
  printf '%-8s %-7s %-24s %-12s %s\n' "$i" "$status" "${code:--}" "${used:--}" "${budget:--}"
  rm -f "$headers"
done
