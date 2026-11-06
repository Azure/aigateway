# Sends chat completions through AI Gateway as two kinds of caller: a runtime API key and your Microsoft Entra
# identity. Telemetry then has an API key ID for the first batch and token claims (tid, oid, appid or azp) for the
# second, so you can attribute both in a chargeback report.
#
# The Entra calls need the AI Gateway Models User role (or AI Gateway User) on the gateway or the model.
#
# Usage:
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   $env:AI_GATEWAY_API_KEY = "..."      # never commit this value
#   az login
#   ./send-attributed-traffic.ps1 -Model <model-name> [-Requests 5]
param(
  [Parameter(Mandatory = $true)][string]$Model,
  [int]$Requests = 5
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a runtime key from Access > Keys' }

$uri = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions"
$runId = "lab14-$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"
$token = az account get-access-token --resource https://azure-api.net/aigateway --query accessToken -o tsv
if (-not $token) { throw 'Could not get a Microsoft Entra token. Run az login first.' }
$body = @{
  model    = $Model
  messages = @(@{ role = 'user'; content = 'In one sentence, what is a chargeback report?' })
} | ConvertTo-Json -Depth 5

function Send-Chat([string]$Caller, [hashtable]$AuthHeader, [string]$CorrelationId) {
  $headers = $AuthHeader + @{ 'x-correlation-id' = $CorrelationId }
  $r = Invoke-WebRequest -Method Post -Uri $uri -Body $body -ContentType 'application/json' -SkipHttpErrorCheck `
    -Headers $headers
  [pscustomobject]@{ Caller = $Caller; Status = $r.StatusCode; 'x-correlation-id' = $CorrelationId }
}

$results = foreach ($i in 1..$Requests) {
  Send-Chat 'api-key' @{ 'api-key' = $env:AI_GATEWAY_API_KEY } "$runId-key-$i"
  Send-Chat 'entra' @{ 'Authorization' = "Bearer $token" } "$runId-entra-$i"
  Start-Sleep -Seconds 1
}
$results | Format-Table -AutoSize
