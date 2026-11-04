# Connects to an AI Gateway MCP server with the MCP Streamable HTTP handshake
# (initialize -> notifications/initialized -> tools/list), prints the published tools, and optionally calls one
# tool. Unlike a plain client, it prints the gateway's answer when a server or tool is blocked, so you can see
# how Agent 365 and gateway controls reach the caller. Requires PowerShell 7 or later.
#
# Usage:
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   $env:AI_GATEWAY_API_KEY = "..."      # never commit this value
#   ./call-tool.ps1 [-Server learn] [-Tool <tool-name>] [-Arguments '<json-object>']
#
# Examples:
#   ./call-tool.ps1 -Server learn
#   ./call-tool.ps1 -Server learn -Tool learn_microsoft_docs_search -Arguments '{"query":"What is Microsoft Agent 365?"}'
#   ./call-tool.ps1 -Server learn -Tool learn_microsoft_docs_fetch -Arguments '{"url":"https://learn.microsoft.com/azure/api-management/agent-365"}'
param(
  [string]$Server = 'learn',
  [string]$Tool,
  [string]$Arguments = '{}'
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a runtime key from Access > Keys' }
$toolArguments = $Arguments | ConvertFrom-Json -AsHashtable
if ($toolArguments -isnot [System.Collections.IDictionary]) { throw '-Arguments must be a JSON object.' }
$uri = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/toolservers/$Server/mcp"
$headers = @{ 'api-key' = $env:AI_GATEWAY_API_KEY; Accept = 'application/json, text/event-stream' }

function Get-Body($Response) {
  if ($Response.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($Response.Content) } else { [string]$Response.Content }
}

# Sends one JSON-RPC message and returns the raw HTTP response. Prints the gateway's answer and stops on non-2xx.
function Send-Mcp([hashtable]$Message, [string]$Step) {
  $r = Invoke-WebRequest -Method Post -Uri $uri -Headers $headers -ContentType 'application/json' `
    -Body ($Message | ConvertTo-Json -Depth 10 -Compress) -TimeoutSec 60 -SkipHttpErrorCheck
  if ($r.StatusCode -lt 200 -or $r.StatusCode -gt 299) {
    $correlation = $r.Headers['x-correlation-id'] | Select-Object -First 1
    Write-Host "${Step}: HTTP $($r.StatusCode)$(if ($correlation) { " (x-correlation-id: $correlation)" })"
    $text = Get-Body $r
    try { Write-Host ($text | ConvertFrom-Json | ConvertTo-Json -Depth 10) } catch { Write-Host $text }
    exit 1
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

Write-Host "MCP endpoint: $uri"

$init = Send-Mcp @{ jsonrpc = '2.0'; id = 1; method = 'initialize'; params = @{
    protocolVersion = '2025-03-26'; capabilities = @{}; clientInfo = @{ name = 'aigateway-labs'; version = '1.0' } } } 'initialize'
$initResponse = Get-RpcResponse $init 1
if (-not $initResponse.result) { throw "initialize returned an error: $($initResponse | ConvertTo-Json -Depth 10 -Compress)" }
$headers['MCP-Protocol-Version'] = $initResponse.result.protocolVersion
$sessionId = $init.Headers['Mcp-Session-Id'] | Select-Object -First 1
if ($sessionId) { $headers['Mcp-Session-Id'] = $sessionId }

Send-Mcp @{ jsonrpc = '2.0'; method = 'notifications/initialized' } 'notifications/initialized' | Out-Null

$listResponse = Send-Mcp @{ jsonrpc = '2.0'; id = 2; method = 'tools/list'; params = @{} } 'tools/list'
$list = Get-RpcResponse $listResponse 2
if ($list.error) { throw "tools/list returned an error: $($list.error | ConvertTo-Json -Compress)" }
Write-Host "tools/list: HTTP $($listResponse.StatusCode)"
$list.result.tools | ForEach-Object { Write-Host "  $($_.name)" }

if (-not $Tool) { return }

Write-Host "`ntools/call: $Tool $Arguments"
$callResponse = Send-Mcp @{ jsonrpc = '2.0'; id = 3; method = 'tools/call'; params = @{
    name = $Tool; arguments = $toolArguments } } 'tools/call'
$call = Get-RpcResponse $callResponse 3
$text = ($call.result.content | Where-Object { $_.type -eq 'text' } | ForEach-Object { $_.text }) -join "`n"

Write-Host "HTTP status: $($callResponse.StatusCode)"
if ($call.error) {
  Write-Host "JSON-RPC error: $($call.error | ConvertTo-Json -Compress)"
} elseif ($call.result.isError) {
  $denial = $call.result._meta.'com.microsoft.azure.ai.gateway/denial'
  Write-Host 'isError: true'
  Write-Host "Denial code: $(if ($denial.code) { $denial.code } else { 'none' })"
  Write-Host "Correlation ID: $(if ($denial.correlationId) { $denial.correlationId } else { 'none' })"
  Write-Host $text
} else {
  Write-Host 'isError: false (the result was returned)'
  Write-Host ($text.Substring(0, [Math]::Min(400, $text.Length)) + "`n...")
}
