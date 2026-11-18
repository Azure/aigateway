# Calls one tool on an AI Gateway MCP server with the MCP Streamable HTTP handshake
# (initialize -> notifications/initialized -> tools/call), and prints whether the result came back or the gateway's
# denial: the JSON-RPC error, or isError with the denial details in _meta.
# Requires PowerShell 7 or later.
#
# Usage:
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   $env:AI_GATEWAY_API_KEY = "<runtime key>"           # Access > API keys; never paste it into a file
#   ./call-tool.ps1 <tool-name> '<arguments as JSON>' [server-name]
#
# Example:
#   ./call-tool.ps1 learn_microsoft_docs_search '{"query": "What is Azure Functions?"}'
param(
  [Parameter(Mandatory, Position = 0)][string]$Tool,
  [Parameter(Position = 1)][string]$Arguments = '{}',
  [Parameter(Position = 2)][string]$Server = 'learn'
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL' }
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a runtime key from Access > API keys' }
try { $toolArguments = $Arguments | ConvertFrom-Json -AsHashtable } catch { throw 'The arguments must be a JSON object.' }
if ($toolArguments -isnot [hashtable]) { throw 'The arguments must be a JSON object.' }

$uri = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/toolservers/$Server/mcp"
$headers = @{
  Authorization = "Bearer $env:AI_GATEWAY_API_KEY"
  Accept        = 'application/json, text/event-stream'
}

function Get-Body($Response) {
  if ($Response.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($Response.Content) } else { [string]$Response.Content }
}

# Sends one JSON-RPC message and returns the raw HTTP response. Stops when the status isn't 2xx.
function Send-Mcp([hashtable]$Message, [string]$Step) {
  $r = Invoke-WebRequest -Method Post -Uri $uri -Headers $headers -ContentType 'application/json' `
    -Body ($Message | ConvertTo-Json -Depth 20 -Compress) -TimeoutSec 120 -SkipHttpErrorCheck
  if ($r.StatusCode -lt 200 -or $r.StatusCode -gt 299) {
    throw "$Step failed with HTTP $($r.StatusCode): $(Get-Body $r)"
  }
  $r
}

# Returns the JSON-RPC response with the given id. The body can be JSON or server-sent events.
function Get-RpcResponse($Response, [int]$Id) {
  $text = Get-Body $Response
  $lines = if ($text -match '(?m)^data:') {
    $text -split "`r?`n" | Where-Object { $_ -like 'data:*' } | ForEach-Object { $_.Substring(5).Trim() }
  } else { @($text) }
  foreach ($line in $lines) {
    try { $message = $line | ConvertFrom-Json } catch { continue }
    if ($message.id -eq $Id) { return $message }
  }
  throw "No JSON-RPC response with id $Id in: $text"
}

$init = Send-Mcp @{ jsonrpc = '2.0'; id = 1; method = 'initialize'; params = @{
    protocolVersion = '2025-06-18'; capabilities = @{}; clientInfo = @{ name = 'aigateway-labs'; version = '1.0' } } } 'initialize'
$initResponse = Get-RpcResponse $init 1
if (-not $initResponse.result) { throw "initialize returned no result: $(Get-Body $init)" }
$headers['MCP-Protocol-Version'] = $initResponse.result.protocolVersion
$sessionId = $init.Headers['Mcp-Session-Id'] | Select-Object -First 1
if ($sessionId) { $headers['Mcp-Session-Id'] = $sessionId }

Send-Mcp @{ jsonrpc = '2.0'; method = 'notifications/initialized' } 'notifications/initialized' | Out-Null

Write-Host "tools/call $Tool $($toolArguments | ConvertTo-Json -Depth 20 -Compress)"
$callResponse = Send-Mcp @{ jsonrpc = '2.0'; id = 2; method = 'tools/call'; params = @{
    name = $Tool; arguments = $toolArguments } } 'tools/call'
$call = Get-RpcResponse $callResponse 2
$text = ($call.result.content | Where-Object { $_.type -eq 'text' } | ForEach-Object { $_.text }) -join "`n"

Write-Host "HTTP status: $($callResponse.StatusCode)"
if ($call.error) {
  Write-Host 'JSON-RPC error:'
  $call.error | ConvertTo-Json -Depth 10
} elseif ($call.result.isError) {
  Write-Host 'isError: true'
  Write-Host $text
  if ($call.result._meta) { $call.result._meta | ConvertTo-Json -Depth 10 }
} else {
  Write-Host 'isError: false (the result was returned)'
  Write-Host $text.Substring(0, [Math]::Min(300, $text.Length))
  Write-Host '...'
}
