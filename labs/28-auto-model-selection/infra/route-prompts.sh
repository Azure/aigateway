#!/usr/bin/env bash
# Sends the simple and hard prompts in prompts.json to an alias, one at a time, and shows which model served each
# one and how many tokens it used, then the totals per model. Each answer stops at 1,000 output tokens to keep the run
# short, which doesn't change which model serves it.
# Usage: ./infra/route-prompts.sh [alias] [objective]
#   objective: optional Balanced, Cost, or Quality, sent as a per-request override that the alias must allow.
# Needs AI_GATEWAY_URL and AI_GATEWAY_API_KEY in the environment, plus curl 7.84 or later and jq.
set -euo pipefail

ALIAS="${1:-auto}"
OBJECTIVE="${2:-}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a gateway runtime API key}"

PROMPTS="$(cd "$(dirname "$0")" && pwd)/prompts.json"
URL="${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions"
TALLY=""

if [ -n "$OBJECTIVE" ]; then
  echo "Sending $(jq length "$PROMPTS") prompts with \"model\": \"$ALIAS\" and the $OBJECTIVE objective"
else
  echo "Sending $(jq length "$PROMPTS") prompts with \"model\": \"$ALIAS\" and the alias's objective"
fi
printf '%3s  %-7s %-24s %7s %7s  %s\n' '#' 'kind' 'served model' 'prompt' 'output' 'text'

i=0
while IFS= read -r ITEM; do
  i=$((i + 1))
  KIND="$(jq -r '.kind' <<<"$ITEM")"
  TEXT="$(jq -r '.prompt' <<<"$ITEM")"
  BODY="$(jq -cn --arg m "$ALIAS" --arg p "$TEXT" --arg o "$OBJECTIVE" \
    '{model: $m, max_completion_tokens: 1000, messages: [{role: "user", content: $p}]}
     + (if $o == "" then {} else {auto_model_selection: {objective: $o}} end)')"

  # Retries a throttled (429) or busy (503) call after the time the gateway asks for.
  for ATTEMPT in 1 2 3 4 5; do
    OUT="$(curl -sS "$URL" -H "Authorization: Bearer $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
      -d "$BODY" -w '\n%{http_code}|%header{retry-after}|%header{x-ms-served-model}')"
    IFS='|' read -r CODE RETRY SERVED <<<"${OUT##*$'\n'}"
    JSON="${OUT%$'\n'*}"
    if [ "$CODE" != "429" ] && [ "$CODE" != "503" ] || [ "$ATTEMPT" = 5 ]; then break; fi
    WAIT="${RETRY:-10}"
    echo "     HTTP $CODE, retrying in ${WAIT}s"
    sleep "$WAIT"
  done

  if [ "$CODE" = "200" ]; then
    IN="$(jq -r '.usage.prompt_tokens // 0' <<<"$JSON")"
    OUTTOK="$(jq -r '.usage.completion_tokens // 0' <<<"$JSON")"
    SERVED="${SERVED:-$(jq -r '.model // "unknown"' <<<"$JSON")}"
  else
    IN=0
    OUTTOK=0
    SERVED="HTTP $CODE $(jq -r '.error.code // empty' <<<"$JSON" 2>/dev/null || true)"
  fi
  printf '%3d  %-7s %-24s %7s %7s  %.50s\n' "$i" "$KIND" "$SERVED" "$IN" "$OUTTOK" "$TEXT"
  TALLY+="${SERVED// /_} $IN $OUTTOK"$'\n'
done < <(jq -c '.[]' "$PROMPTS")

echo
echo "Requests and tokens per model:"
printf '%s' "$TALLY" | awk '{ n[$1]++; p[$1] += $2; c[$1] += $3 }
  END { for (m in n) printf "%-24s %3d requests %7d prompt tokens %7d output tokens\n", m, n[m], p[m], c[m] }' | sort
