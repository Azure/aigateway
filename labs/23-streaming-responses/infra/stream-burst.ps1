# Sends a burst of streamed chat completions through AI Gateway and prints, for each request, the status code,
# Retry-After, how many server-sent events arrived, and the tokens in the usage chunk if the stream had one.
# Run it without -Usage and then with -Usage to see that a token limit counts streamed tokens either way.
#
# Usage (PowerShell 7.4 or later):
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   $env:AI_GATEWAY_API_KEY = "..."      # never commit this value
#   ./stream-burst.ps1 -Model <model-name> [-Requests 8] [-Usage]
param(
  [Parameter(Mandatory = $true)][string]$Model,
  [int]$Requests = 8,
  [switch]$Usage
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a runtime key from Access > Keys' }

$uri = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions"
# Each request asks for about 200 output tokens, the same prompt as lab 06.
$body = @{
  model                 = $Model
  stream                = $true
  max_completion_tokens = 250
  reasoning_effort      = 'none'
  messages              = @(@{ role = 'user'; content = 'Write a 150-word product update about an AI gateway that governs models and tools.' })
}
if ($Usage) { $body.stream_options = @{ include_usage = $true } }
$json = $body | ConvertTo-Json -Depth 5

1..$Requests | ForEach-Object {
  # The script reads each body in full, so Invoke-WebRequest is enough here.
  $r = Invoke-WebRequest -Method Post -Uri $uri -Body $json -ContentType 'application/json' `
    -Headers @{ 'api-key' = $env:AI_GATEWAY_API_KEY } -SkipHttpErrorCheck
  $content = if ($r.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($r.Content) } else { $r.Content }
  if ($r.StatusCode -eq 200) {
    $chunks = @($content -split "`n" | Where-Object { $_.StartsWith('data: {') } | ForEach-Object { $_.Substring(6) | ConvertFrom-Json })
    $last = $chunks | Where-Object { $_.usage } | Select-Object -Last 1
    $events = $chunks.Count
    $used = if ($last) { "$($last.usage.total_tokens) tokens" } else { 'none' }
  } else {
    $events = '-'
    $used = try { ($content | ConvertFrom-Json).message } catch { $content }
  }
  [pscustomobject]@{
    Request       = $_
    Status        = $r.StatusCode
    'Retry-After' = ($r.Headers['Retry-After'] | Select-Object -First 1) ?? '-'
    Events        = $events
    'Usage chunk' = $used
  }
} | Format-Table -AutoSize | Out-String -Width 160
