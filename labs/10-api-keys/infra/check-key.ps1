<#
.SYNOPSIS
  Sends one small Chat Completions request through AI Gateway and reports whether the gateway accepted the
  runtime API key. Only the last four characters of the key are printed.

.EXAMPLE
  $env:AI_GATEWAY_URL     = "<gateway-url>"
  $env:AI_GATEWAY_MODEL   = "<model-name>"
  $env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
  ./check-key.ps1 -Label "app-dev"

.EXAMPLE
  ./check-key.ps1 -ApiKey $oldKey -Label "old value"

.EXAMPLE
  ./check-key.ps1 -NoKey
#>
[CmdletBinding()]
param(
  [string]$ApiKey = $env:AI_GATEWAY_API_KEY,
  [string]$Label = "current key",
  [switch]$NoKey
)
$ErrorActionPreference = "Stop"

if (-not $env:AI_GATEWAY_URL)   { throw "Set `$env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com" }
if (-not $env:AI_GATEWAY_MODEL) { throw "Set `$env:AI_GATEWAY_MODEL to a callable model alias" }

$uri  = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions"
$body = @{ model = $env:AI_GATEWAY_MODEL; messages = @(@{ role = "user"; content = "ping" }) } | ConvertTo-Json -Depth 5

$headers = @{}
if ($NoKey) {
  $Label = "no key"
  $hint  = "-"
} else {
  if (-not $ApiKey) { throw "Pass -ApiKey or set `$env:AI_GATEWAY_API_KEY to the runtime key to test" }
  $headers["api-key"] = $ApiKey
  $hint = "..." + $ApiKey.Substring([Math]::Max(0, $ApiKey.Length - 4))
}

try {
  $response = Invoke-WebRequest -Method Post -Uri $uri -Headers $headers -ContentType "application/json" `
    -Body $body -SkipHttpErrorCheck
  $status  = $response.StatusCode
  $content = "$($response.Content)"
} catch {
  Write-Warning $_.Exception.Message
  $status  = 0
  $content = ""
}

$result = switch ($status) {
  { $_ -ge 200 -and $_ -lt 300 } { "accepted"; break }
  401     { "rejected: the key is missing, invalid, rotated, suspended, or deleted"; break }
  { $_ -eq 404 -and $content -match 'model_not_found' } {
    "not checked: the gateway doesn't know the alias in AI_GATEWAY_MODEL"; break
  }
  0       { "no response: check AI_GATEWAY_URL and your network"; break }
  default { "key accepted, but the call failed: check AI_GATEWAY_MODEL and the gateway's policies" }
}

"{0,-14} {1,-8} HTTP {2}  {3}" -f $Label, $hint, $(if ($status) { $status } else { "---" }), $result
