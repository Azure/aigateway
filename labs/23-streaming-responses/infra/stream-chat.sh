#!/usr/bin/env bash
# Streams a Chat Completions response through AI Gateway, prints the reply as it arrives, then prints how many
# server-sent events came back, how many had an empty choices array, the time to the first token, and the usage
# chunk if the stream ended with one.
#
# Usage:
#   export AI_GATEWAY_URL="<gateway-url>"
#   export AI_GATEWAY_MODEL="<model-name>"
#   export AI_GATEWAY_API_KEY="..."      # never commit this value
#   ./stream-chat.sh [--usage] [--raw] ["Your prompt"]
#
#   --usage  sets stream_options.include_usage to true, so the stream ends with a usage chunk
#   --raw    prints every server-sent event line instead of the reply text
# Requires curl and jq 1.6 or later.
set -euo pipefail

USAGE=false
RAW=false
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --usage) USAGE=true ;;
    --raw) RAW=true ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
PROMPT="${1:-Explain in three short sentences why streaming makes chat apps feel faster.}"
: "${AI_GATEWAY_URL:?Set AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com}"
: "${AI_GATEWAY_MODEL:?Set AI_GATEWAY_MODEL to the callable model alias}"
: "${AI_GATEWAY_API_KEY:?Set AI_GATEWAY_API_KEY to a runtime key from Access > Keys}"

# reasoning_effort none spends the budget on the reply instead of hidden reasoning, so the first token arrives sooner.
BODY=$(jq -n --arg m "$AI_GATEWAY_MODEL" --arg p "$PROMPT" --argjson usage "$USAGE" '
  {model: $m, stream: true, max_completion_tokens: 300, reasoning_effort: "none",
   messages: [{role: "user", content: $p}]}
  + (if $usage then {stream_options: {include_usage: true}} else {} end)')

headers=$(mktemp)
trap 'rm -f "$headers"' EXIT

# -N turns off curl's output buffering. jq reads the raw lines as they arrive and keeps running totals.
curl -sSN -D "$headers" "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" -d "$BODY" \
| jq -nRrj --unbuffered --argjson raw "$RAW" '
    def secs: (. * 100 | round) / 100 | tostring + " s";
    def summary:
      "\n\n"
      + (if .events == 0 then "Response body       \(.other)\n"
         else "Events              \(.events) (\(.empty) with an empty choices array)\n"
            + "First token         \(if .ttft then (.ttft | secs) else "-" end)\n"
            + "Usage chunk         "
            + (if .usage then "prompt \(.usage.prompt_tokens), completion \(.usage.completion_tokens), total \(.usage.total_tokens)"
               else "none: run again with --usage to ask for one" end) + "\n"
         end);
    foreach (inputs, null) as $line (
      {t0: now, events: 0, empty: 0, ttft: null, usage: null, other: "", out: ""};
      .out = ""
      | if $line == null then .end = true
        elif ($line | startswith("data: ")) then
          ($line[6:]) as $data
          | if $data == "[DONE]" then .out = (if $raw then $line + "\n" else "" end)
            else ($data | fromjson) as $chunk
              | ([$chunk.choices[]?.delta.content // empty] | join("")) as $text
              | .events += 1
              | .empty += (if ($chunk.choices // []) == [] then 1 else 0 end)
              | .usage = ($chunk.usage // .usage)
              | .ttft = (if .ttft == null and $text != "" then now - .t0 else .ttft end)
              | .out = (if $raw then $line + "\n" else $text end)
            end
        else .other += $line
        end;
      if .end then summary else .out end)'

status=$(awk 'toupper($1) ~ /^HTTP/ {code=$2} END {print code}' "$headers")
type=$(awk -F': ' 'tolower($1)=="content-type" {gsub("\r","",$2); print $2}' "$headers")
served=$(awk -F': ' 'tolower($1)=="x-ms-served-model" {gsub("\r","",$2); print $2}' "$headers")
retry=$(awk -F': ' 'tolower($1)=="retry-after" {gsub("\r","",$2); print $2}' "$headers")
printf 'HTTP status         %s\n' "$status"
printf 'Content-Type        %s\n' "${type:--}"
printf 'Served by           %s\n' "${served:--}"
[[ -n "$retry" ]] && printf 'Retry-After         %s\n' "$retry"
[[ "$status" == 200 ]]
