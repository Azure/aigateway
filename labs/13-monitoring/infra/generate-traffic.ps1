# Sends a small mix of chat completions through AI Gateway so the Monitoring dashboard has data to show.
# Every request carries an x-correlation-id header. The last request asks for an alias that doesn't exist,
# so you also get one failed request to find in Monitoring › Traces.
#
# Usage:
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   $env:AI_GATEWAY_API_KEY = "..."      # never commit this value
#   ./generate-traffic.ps1 -Model <model-name> [-Requests 10]
param(
  [Parameter(Mandatory = $true)][string]$Model,
  [int]$Requests = 10
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a runtime key from Access > Keys' }

$uri = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions"
$runId = "lab13-$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"
$prompts = @(
  'Summarize what an AI gateway does in one sentence.',
  'List three reasons to apply policies in front of model calls.',
  'Write a haiku about observability.',
  'Explain an OpenTelemetry trace to a new developer in two sentences.'
)

function Send-Chat([string]$ModelName, [string]$Prompt, [string]$CorrelationId) {
  $body = @{
    model    = $ModelName
    messages = @(@{ role = 'user'; content = $Prompt })
  } | ConvertTo-Json -Depth 5
  $r = Invoke-WebRequest -Method Post -Uri $uri -Body $body -ContentType 'application/json' -SkipHttpErrorCheck `
    -Headers @{ 'api-key' = $env:AI_GATEWAY_API_KEY; 'x-correlation-id' = $CorrelationId }
  [pscustomobject]@{ Request = $null; Model = $ModelName; Status = $r.StatusCode; 'x-correlation-id' = $CorrelationId }
}

$results = foreach ($i in 1..$Requests) {
  $row = Send-Chat $Model $prompts[($i - 1) % $prompts.Count] "$runId-$i"
  $row.Request = $i
  $row
  Start-Sleep -Seconds 1
}
$errorRow = Send-Chat 'does-not-exist' "This alias isn't published." "$runId-error"
$errorRow.Request = 'error'
@($results) + $errorRow | Format-Table -AutoSize
