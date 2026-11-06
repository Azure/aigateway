# Sends one chat completion through AI Gateway and prints the status code, so you can check how the
# gateway-wide baseline treats a call from this machine: 200 when it passes, 403 when the IP filter
# drops it, 429 when a rate limit applies, or 400 when content safety blocks it.
# Requires PowerShell 7 or later.
#
# Usage:
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   $env:AI_GATEWAY_API_KEY = "..."      # never commit this value
#   ./check-call.ps1 -Model <model-name>
param(
  [Parameter(Mandatory)][string]$Model
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a runtime key from Access > Keys' }

$uri = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions"
$body = @{
  model                 = $Model
  max_completion_tokens = 60
  reasoning_effort      = 'none'
  messages              = @(@{ role = 'user'; content = 'In one sentence, what is a gateway-wide policy baseline?' })
} | ConvertTo-Json -Depth 5 -Compress

$r = Invoke-WebRequest -Method Post -Uri $uri -Body $body -ContentType 'application/json' `
  -Headers @{ 'api-key' = $env:AI_GATEWAY_API_KEY } -TimeoutSec 120 -SkipHttpErrorCheck
$content = if ($r.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($r.Content) } else { [string]$r.Content }

Write-Host "Status: $([int]$r.StatusCode)"
if ([int]$r.StatusCode -eq 200) {
  $reply = (($content | ConvertFrom-Json).choices[0].message.content -replace '\s+', ' ').Trim()
  Write-Host "Reply:  $reply"
} else {
  Write-Host "Body:   $($content.Substring(0, [Math]::Min(400, $content.Length)))"
}
