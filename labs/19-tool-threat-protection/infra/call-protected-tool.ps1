# Calls one tool on an AI Gateway MCP server that has Agent 365 tool threat protection, using the MCP
# Streamable HTTP handshake (initialize -> notifications/initialized -> tools/list -> tools/call).
# Prints whether the tool result came back, or the denial code and correlation ID the gateway returned.
# Requires PowerShell 7 or later.
#
# Usage:
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   ./call-protected-tool.ps1 -Auth token [-Server learn] [-Query "..."]   # delegated Entra token for the signed-in az user
#   ./call-protected-tool.ps1 -Auth key   [-Server learn] [-Query "..."]   # runtime key in $env:AI_GATEWAY_API_KEY
#
# -Auth token uses $env:AI_GATEWAY_TOKEN when set, otherwise it runs
#   az account get-access-token --resource https://azure-api.net/aigateway
# The script calls the Learn docs search tool (or the first tool whose name contains "search") unless you
# pass -Tool, and sends the query as {"query": "..."}. Use a benign query.
param(
  [Parameter(Mandatory)][ValidateSet('token', 'key')][string]$Auth,
  [string]$Server = 'learn',
  [string]$Query = 'What is Azure API Management?',
  [string]$Tool
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
$uri = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/toolservers/$Server/mcp"
$headers = @{ Accept = 'application/json, text/event-stream' }

if ($Auth -eq 'token') {
  $token = $env:AI_GATEWAY_TOKEN
  if (-not $token) {
    $token = az account get-access-token --resource https://azure-api.net/aigateway --query accessToken -o tsv
    if ($LASTEXITCODE -ne 0 -or -not $token) { throw 'Could not get a token. Run az login first.' }
  }
  # Delegated (user) tokens carry an scp claim. App-only tokens carry roles instead and can't be used for evaluation.
  try {
    $payload = $token.Split('.')[1].Replace('-', '+').Replace('_', '/')
    $payload = $payload.PadRight($payload.Length + (4 - $payload.Length % 4) % 4, '=')
    $claims = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($payload)) | ConvertFrom-Json
  } catch { $claims = $null }
  if ($claims.scp) { Write-Host "Delegated token for the signed-in user (scp: $($claims.scp))" }
  else { Write-Warning "The token has no scp claim, so it isn't a delegated user token." }
  $headers['Authorization'] = "Bearer $token"
} else {
  if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a runtime key from Access > Keys' }
  $headers['api-key'] = $env:AI_GATEWAY_API_KEY
}

function Get-Body($Response) {
  if ($Response.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($Response.Content) } else { [string]$Response.Content }
}

# Sends one JSON-RPC message and returns the raw HTTP response. Stops when the status isn't 2xx.
function Send-Mcp([hashtable]$Message, [string]$Step) {
  $r = Invoke-WebRequest -Method Post -Uri $uri -Headers $headers -ContentType 'application/json' `
    -Body ($Message | ConvertTo-Json -Depth 10 -Compress) -TimeoutSec 120 -SkipHttpErrorCheck
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
Write-Host "tools/list: HTTP $($listResponse.StatusCode), $(@($list.result.tools).Count) tools (discovery isn't evaluated)"

if (-not $Tool) {
  $names = @($list.result.tools | ForEach-Object { $_.name })
  $Tool = @(($names | Where-Object { $_ -match 'docs_search' }) + ($names | Where-Object { $_ -match 'search' }))[0]
}
if (-not $Tool) { throw "No tool name contains 'search'. Pass -Tool with the tool to call." }

Write-Host "tools/call: $Tool with query: $Query"
$callResponse = Send-Mcp @{ jsonrpc = '2.0'; id = 3; method = 'tools/call'; params = @{
    name = $Tool; arguments = @{ query = $Query } } } 'tools/call'
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
