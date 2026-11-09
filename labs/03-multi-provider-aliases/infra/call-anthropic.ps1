# Calls a model through AI Gateway with the native Anthropic Messages API and prints the HTTP status,
# the backend model that answered, and the reply. The gateway passes the request through unchanged,
# so the body and the response use Anthropic's format. Requires PowerShell 7 or later.
#
# Usage:
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   $env:AI_GATEWAY_API_KEY = "..."      # your gateway runtime key, never the provider key; never commit it
#   ./call-anthropic.ps1 -Alias <alias> [-Prompt "Your prompt"]
param(
  [Parameter(Mandatory = $true)][string]$Alias,
  [string]$Prompt = 'In one sentence, what is an AI gateway?'
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a runtime key from Access > Keys' }

$uri = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/anthropic/v1/messages"
$headers = @{
  'api-key'           = $env:AI_GATEWAY_API_KEY
  'anthropic-version' = '2023-06-01'
}
$body = @{
  model      = $Alias
  max_tokens = 1024
  messages   = @(@{ role = 'user'; content = $Prompt })
} | ConvertTo-Json -Depth 5

$r = Invoke-WebRequest -Method Post -Uri $uri -Headers $headers -ContentType 'application/json' -Body $body -SkipHttpErrorCheck

"Alias:   $Alias"
"Status:  $($r.StatusCode)"
if ($r.StatusCode -eq 200) {
  $json = $r.Content | ConvertFrom-Json
  "Model:   $($json.model)"
  "Reply:   $((@($json.content) | Where-Object { $_.type -eq 'text' } | ForEach-Object { $_.text }) -join '')"
}
else {
  "Body:    $($r.Content)"
  exit 1
}
