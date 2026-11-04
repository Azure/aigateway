# Sends a burst of MCP requests to an AI Gateway MCP server and prints the HTTP status and
# Retry-After header of each one so you can watch a request rate limit engage.
# Every HTTP request counts as a call, including the two handshake messages. Requires PowerShell 7 or later.
#
# Usage:
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   $env:AI_GATEWAY_API_KEY = "..."      # never commit this value
#   ./trigger-request-rate.ps1 [-Server learn] [-Requests 8]
#
# Set $env:AI_GATEWAY_MCP_ENDPOINT to use a full MCP endpoint URL instead of building it from AI_GATEWAY_URL.
param(
  [string]$Server = 'learn',
  [int]$Requests = 8
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a runtime key from Access > Keys' }
$uri = $env:AI_GATEWAY_MCP_ENDPOINT
if (-not $uri) {
  if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
  $uri = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/toolservers/$Server/mcp"
}
$headers = @{ 'api-key' = $env:AI_GATEWAY_API_KEY; Accept = 'application/json, text/event-stream' }
$script:count = 0
$rows = [System.Collections.Generic.List[object]]::new()

function Get-Body($Response) {
  if ($Response.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($Response.Content) } else { [string]$Response.Content }
}

# Sends one JSON-RPC message, records one result row, and returns the raw HTTP response.
function Send-Mcp([string]$Label, [hashtable]$Message) {
  $r = Invoke-WebRequest -Method Post -Uri $uri -Headers $headers -ContentType 'application/json' `
    -Body ($Message | ConvertTo-Json -Depth 10 -Compress) -TimeoutSec 60 -SkipHttpErrorCheck
  $script:count++
  $retry = $r.Headers['Retry-After'] | Select-Object -First 1
  $rows.Add([pscustomobject]@{ Request = $script:count; Method = $Label; Status = [int]$r.StatusCode; 'Retry-After' = ($retry ?? '-') })
  $r
}

Write-Host "MCP endpoint: $uri"

$init = Send-Mcp 'initialize' @{ jsonrpc = '2.0'; id = 1; method = 'initialize'; params = @{
    protocolVersion = '2025-03-26'; capabilities = @{}; clientInfo = @{ name = 'aigateway-labs'; version = '1.0' } } }
$text = Get-Body $init
$lines = if ($text -match '(?m)^data:') {
  $text -split "`r?`n" | Where-Object { $_ -like 'data:*' } | ForEach-Object { $_.Substring(5).Trim() }
} else { @($text) }
foreach ($line in $lines) {
  try { $message = $line | ConvertFrom-Json } catch { continue }
  if ($message.result.protocolVersion) { $headers['MCP-Protocol-Version'] = $message.result.protocolVersion; break }
}
$sessionId = $init.Headers['Mcp-Session-Id'] | Select-Object -First 1
if ($sessionId) { $headers['Mcp-Session-Id'] = $sessionId }

Send-Mcp 'notifications/initialized' @{ jsonrpc = '2.0'; method = 'notifications/initialized' } | Out-Null

$last = $null
foreach ($i in 1..$Requests) {
  $last = Send-Mcp 'tools/list' @{ jsonrpc = '2.0'; id = $i + 1; method = 'tools/list'; params = @{} }
}

$rows | Format-Table -AutoSize | Out-String | Write-Host
if ($last -and [int]$last.StatusCode -eq 429) {
  Write-Host "Last response body:"
  Write-Host (Get-Body $last)
}
