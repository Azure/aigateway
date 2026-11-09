# Sends a series of chat completions through AI Gateway and prints the status code, the error
# code, and the tokens used, so you can watch a cost limit block a caller with 403
# LlmCostQuotaExceeded. The last column lists any response header whose name mentions
# budget, cost, or remaining, so you can spot the remaining-budget header.
#
# Usage:
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   $env:AI_GATEWAY_API_KEY = "..."      # never commit this value
#   ./trigger-cost-limit.ps1 -Model <model-name> [-Requests 10]
param(
  [Parameter(Mandatory = $true)][string]$Model,
  [int]$Requests = 10
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a runtime key from Access > Keys' }

$uri = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions"
# reasoning_effort none spends the budget on the reply instead of hidden reasoning, so token counts stay predictable.
$body = @{
  model                 = $Model
  max_completion_tokens = 250
  reasoning_effort      = 'none'
  messages              = @(@{ role = 'user'; content = 'Write a 150-word note to a finance team explaining why per-app AI budgets help.' })
} | ConvertTo-Json -Depth 5

1..$Requests | ForEach-Object {
  $r = Invoke-WebRequest -Method Post -Uri $uri -Body $body -ContentType 'application/json' `
    -Headers @{ 'api-key' = $env:AI_GATEWAY_API_KEY } -SkipHttpErrorCheck
  $used = '-'
  $code = '-'
  if ($r.StatusCode -eq 200) {
    $used = ($r.Content | ConvertFrom-Json).usage.total_tokens
  } elseif ($r.Content -match '"code"\s*:\s*"([^"]+)"') {
    $code = $Matches[1]
  }
  $budget = ($r.Headers.Keys | Where-Object { $_ -match 'budget|cost|remaining' } |
    ForEach-Object { "$_=$($r.Headers[$_] | Select-Object -First 1)" }) -join '; '
  [pscustomobject]@{
    Request          = $_
    Status           = $r.StatusCode
    'Error code'     = $code
    'Tokens used'    = $used
    'Budget headers' = if ($budget) { $budget } else { '-' }
  }
} | Format-Table -AutoSize
