# Connects to an AI Gateway MCP server with the MCP Streamable HTTP handshake
# (initialize -> notifications/initialized -> tools/list), prints the published tools,
# and optionally calls one tool with a {"query": "..."} argument. Requires PowerShell 7 or later.
#
# Usage:
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   $env:AI_GATEWAY_API_KEY = "..."      # never commit this value
#   ./list-tools.ps1 [-Server learn] [-Tool <tool-name>] [-Query "..."]
#
# Examples:
#   ./list-tools.ps1 -Server learn
#   ./list-tools.ps1 -Server learn -Tool learn_microsoft_docs_search -Query "What is AI Gateway?"
#
# Set $env:AI_GATEWAY_MCP_ENDPOINT to use a full MCP endpoint URL instead of building it from AI_GATEWAY_URL.
param(
  [string]$Server = 'learn',
  [string]$Tool,
  [string]$Query = 'What is Azure AI Gateway?'
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a runtime key from Access > Keys' }
$uri = $env:AI_GATEWAY_MCP_ENDPOINT
if (-not $uri) {
  if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
  $uri = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/toolservers/$Server/mcp"
}
$headers = @{ 'api-key' = $env:AI_GATEWAY_API_KEY; Accept = 'application/json, text/event-stream' }

# Sends one JSON-RPC message and returns the raw HTTP response.
function Send-Mcp([hashtable]$Message, [string]$Step) {
  $r = Invoke-WebRequest -Method Post -Uri $uri -Headers $headers -ContentType 'application/json' `
    -Body ($Message | ConvertTo-Json -Depth 10 -Compress) -TimeoutSec 60 -SkipHttpErrorCheck
  if ($r.StatusCode -lt 200 -or $r.StatusCode -gt 299) {
    throw "$Step failed with HTTP $($r.StatusCode): $(Get-Body $r)"
  }
  $r
}

function Get-Body($Response) {
  if ($Response.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($Response.Content) } else { [string]$Response.Content }
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
Write-Host "Server: $($initResponse.result.serverInfo.name)  protocol: $($initResponse.result.protocolVersion)"

Send-Mcp @{ jsonrpc = '2.0'; method = 'notifications/initialized' } 'notifications/initialized' | Out-Null

$list = Get-RpcResponse (Send-Mcp @{ jsonrpc = '2.0'; id = 2; method = 'tools/list'; params = @{} } 'tools/list') 2
if ($list.error) { throw "tools/list returned an error: $($list.error | ConvertTo-Json -Compress)" }
$list.result.tools | ForEach-Object {
  $description = ([string]$_.description -replace '\s+', ' ')
  [pscustomobject]@{ Tool = $_.name; Description = $description.Substring(0, [Math]::Min(70, $description.Length)) }
} | Format-Table -AutoSize | Out-String | Write-Host
Write-Host "$(@($list.result.tools).Count) tools published"

if ($Tool) {
  Write-Host "`nCalling $Tool with query: $Query"
  $call = Get-RpcResponse (Send-Mcp @{ jsonrpc = '2.0'; id = 3; method = 'tools/call'; params = @{
        name = $Tool; arguments = @{ query = $Query } } } 'tools/call') 3
  if ($call.error -or $call.result.isError) { throw "The tool call failed: $($call | ConvertTo-Json -Depth 10 -Compress)" }
  $text = ($call.result.content | Where-Object { $_.type -eq 'text' } | ForEach-Object { $_.text }) -join "`n"
  Write-Host ($text.Substring(0, [Math]::Min(600, $text.Length)) + "`n...")
}
