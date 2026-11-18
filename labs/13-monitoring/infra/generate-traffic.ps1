# Sends a small mix of model and MCP calls through AI Gateway, so the Monitoring dashboard has data to show and
# failures to investigate:
#   - <Requests> chat completions to your alias, which succeed
#   - a request for an alias that doesn't exist, which the gateway rejects with 404
#   - a message with an invalid role, which the model provider rejects with 400
#   - with -ToolServer, such as learn from lab 04, a tools/call without the tool's required argument: the
#     response is HTTP 200, but the tool reports isError, so the trace marks the tool call as failed
#
# Usage:
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   $env:AI_GATEWAY_API_KEY = "..."      # never commit this value
#   ./generate-traffic.ps1 -Model <model-name> [-Requests 10] [-ToolServer learn]
param(
  [Parameter(Mandatory = $true)][string]$Model,
  [int]$Requests = 10,
  [string]$ToolServer = ''
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a runtime key from Access > API keys' }

$base = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default"
$headers = @{ Authorization = "Bearer $env:AI_GATEWAY_API_KEY" }
$prompts = @(
  'Summarize what an AI gateway does in one sentence.',
  'List three reasons to apply policies in front of model calls.',
  'Write a haiku about observability.',
  'Explain an OpenTelemetry trace to a new developer in two sentences.'
)

function Send-Chat([string]$ModelName, [string]$Role, [string]$Prompt) {
  $body = @{ model = $ModelName; messages = @(@{ role = $Role; content = $Prompt }) } | ConvertTo-Json -Depth 5
  $r = Invoke-WebRequest -Method Post -Uri "$base/models/openai/v1/chat/completions" -Body $body `
    -ContentType 'application/json' -Headers $headers -SkipHttpErrorCheck
  "$($r.StatusCode)"
}

$results = foreach ($i in 1..$Requests) {
  [pscustomobject]@{ Request = $i; Target = $Model; Status = Send-Chat $Model 'user' $prompts[($i - 1) % $prompts.Count]; Expected = '200' }
  Start-Sleep -Seconds 1
}
$results = @($results)
$results += [pscustomobject]@{ Request = 'fail-1'; Target = 'does-not-exist'; Status = Send-Chat 'does-not-exist' 'user' "This alias isn't published."; Expected = '404, unknown alias' }
$results += [pscustomobject]@{ Request = 'fail-2'; Target = $Model; Status = Send-Chat $Model 'robot' "robot isn't a valid role."; Expected = '400, from the provider' }

if ($ToolServer) {
  # learn_microsoft_docs_fetch requires a url argument, so the tool runs and reports an error
  $call = '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"learn_microsoft_docs_fetch","arguments":{}}}'
  $r = Invoke-WebRequest -Method Post -Uri "$base/toolservers/$ToolServer/mcp" -Body $call -ContentType 'application/json' `
    -Headers ($headers + @{ Accept = 'application/json, text/event-stream'; 'MCP-Protocol-Version' = '2025-06-18' }) -SkipHttpErrorCheck
  $status = "$($r.StatusCode)"
  if ("$($r.Content)" -match '"isError":\s*true') { $status += ' isError' }
  $results += [pscustomobject]@{ Request = 'fail-3'; Target = "${ToolServer}: learn_microsoft_docs_fetch"; Status = $status; Expected = '200 isError, tool error' }
}
$results | Format-Table -AutoSize
