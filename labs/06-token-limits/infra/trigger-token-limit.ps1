# Sends a burst of chat completions through AI Gateway and prints the status code, Retry-After, the tokens
# each call used, and the backend deployment's own x-ratelimit-remaining-tokens header, so you can watch a
# gateway token limit engage while the backend still has capacity.
#
# Usage:
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   $env:AI_GATEWAY_API_KEY = "..."      # never commit this value
#   ./trigger-token-limit.ps1 -Model <model-name> [-Requests 8]
param(
  [Parameter(Mandatory = $true)][string]$Model,
  [int]$Requests = 8
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
  messages              = @(@{ role = 'user'; content = 'Write a 150-word product update about an AI gateway that governs models and tools.' })
} | ConvertTo-Json -Depth 5

1..$Requests | ForEach-Object {
  $r = Invoke-WebRequest -Method Post -Uri $uri -Body $body -ContentType 'application/json' `
    -Headers @{ 'api-key' = $env:AI_GATEWAY_API_KEY } -SkipHttpErrorCheck
  $used = if ($r.StatusCode -eq 200) { ($r.Content | ConvertFrom-Json).usage.total_tokens } else { '-' }
  [pscustomobject]@{
    Request           = $_
    Status            = $r.StatusCode
    'Retry-After'         = ($r.Headers['Retry-After'] | Select-Object -First 1) ?? '-'
    'Tokens used'         = $used
    'Backend tokens left' = ($r.Headers['x-ratelimit-remaining-tokens'] | Select-Object -First 1) ?? '-'
  }
} | Format-Table -AutoSize
