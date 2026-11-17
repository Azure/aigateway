# Calls the obo-demo MCP server of lab 33 through Azure AI Gateway as the signed-in az user, and checks each link of
# the on-behalf-of chain:
#   1. A call without a token gets 401 from the gateway.
#   2. The MCP handshake (initialize -> notifications/initialized -> tools/list) with your token for the gateway.
#   3. demo_whoami returns the claims of the token that the backend received: the same user (oid), issued for the
#      backend's API (aud), and requested by the token exchange app (azp).
#   4. When $env:BACKEND_URL is set, your gateway token sent straight to the backend gets 401: only the exchanged token works.
# Requires PowerShell 7 or later.
#
# Usage:
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   $env:BACKEND_URL = "<backend-url>"   # optional, enables check 4
#   ./call-obo-tool.ps1 [-Server obo-demo]
#
# The script uses $env:AI_GATEWAY_TOKEN when set, otherwise it runs
#   az account get-access-token --scope https://ai.gateway.azure.com/Data.All
# It never prints a token.
param(
  [string]$Server = 'obo-demo'
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
$uri = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/toolservers/$Server/mcp"
$init = @{ jsonrpc = '2.0'; id = 1; method = 'initialize'; params = @{
    protocolVersion = '2025-06-18'; capabilities = @{}; clientInfo = @{ name = 'aigateway-labs'; version = '1.0' } } }
$initJson = $init | ConvertTo-Json -Depth 10 -Compress

function Get-Claims([string]$Jwt) {
  try {
    $payload = $Jwt.Split('.')[1].Replace('-', '+').Replace('_', '/')
    $payload = $payload.PadRight($payload.Length + (4 - $payload.Length % 4) % 4, '=')
    [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($payload)) | ConvertFrom-Json
  } catch { [pscustomobject]@{} }
}

function Get-Body($Response) {
  if ($Response.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($Response.Content) } else { [string]$Response.Content }
}

Write-Host "MCP endpoint: $uri"

# 1. Without a token.
$anon = Invoke-WebRequest -Method Post -Uri $uri -ContentType 'application/json' -Body $initJson -TimeoutSec 60 `
  -Headers @{ Accept = 'application/json, text/event-stream' } -SkipHttpErrorCheck
if ($anon.StatusCode -eq 401) { Write-Host '1. Without a token: HTTP 401, as expected' }
else { Write-Warning "1. Without a token: HTTP $($anon.StatusCode) (expected 401)" }

$token = $env:AI_GATEWAY_TOKEN
if (-not $token) {
  $token = az account get-access-token --scope https://ai.gateway.azure.com/Data.All --query accessToken -o tsv
  if ($LASTEXITCODE -ne 0 -or -not $token) { throw 'Could not get a token. Run az login first.' }
}
$caller = Get-Claims $token
Write-Host "   Your token for the gateway: aud $($caller.aud) scp $($caller.scp) oid $($caller.oid)"
$headers = @{ Accept = 'application/json, text/event-stream'; Authorization = "Bearer $token" }

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

# 2. The handshake.
$initResult = Send-Mcp $init 'initialize'
$initResponse = Get-RpcResponse $initResult 1
if (-not $initResponse.result) { throw "initialize returned an error: $($initResponse | ConvertTo-Json -Depth 10 -Compress)" }
$protocol = $initResponse.result.protocolVersion
$headers['MCP-Protocol-Version'] = $protocol
$sessionId = $initResult.Headers['Mcp-Session-Id'] | Select-Object -First 1
if ($sessionId) { $headers['Mcp-Session-Id'] = $sessionId }

Send-Mcp @{ jsonrpc = '2.0'; method = 'notifications/initialized' } 'notifications/initialized' | Out-Null

$list = Get-RpcResponse (Send-Mcp @{ jsonrpc = '2.0'; id = 2; method = 'tools/list'; params = @{} } 'tools/list') 2
if ($list.error) { throw "tools/list returned an error: $($list.error | ConvertTo-Json -Depth 10 -Compress)" }
$names = @($list.result.tools.name)
Write-Host "2. Handshake: MCP version $protocol, tools: $($names -join ', ')"

# 3. whoami.
$tool = $names | Where-Object { $_ -like '*whoami' } | Select-Object -First 1
if (-not $tool) { throw 'No tool name ends with whoami.' }
$call = Get-RpcResponse (Send-Mcp @{ jsonrpc = '2.0'; id = 3; method = 'tools/call'; params = @{ name = $tool; arguments = @{} } } 'tools/call') 3
if ($call.error -or $call.result.isError) { throw "tools/call $tool failed: $($call | ConvertTo-Json -Depth 10 -Compress)" }
$who = if ($call.result.structuredContent) { $call.result.structuredContent } else { $call.result.content[0].text | ConvertFrom-Json }
Write-Host "3. ${tool}: the backend received this token:"
$who | Select-Object name, username, object_id, audience, client_app_id, scopes | Format-List | Out-String | Write-Host
if ($who.object_id -eq $caller.oid) {
  Write-Host '   Same user as your token for the gateway, different audience: the gateway exchanged it on your behalf'
} else {
  Write-Warning "The backend saw a different user than your token's oid ($($caller.oid))"
}

# 4. Your gateway token, straight to the backend.
if ($env:BACKEND_URL) {
  $direct = Invoke-WebRequest -Method Post -Uri $env:BACKEND_URL -ContentType 'application/json' -Body $initJson -TimeoutSec 60 `
    -Headers @{ Accept = 'application/json, text/event-stream'; Authorization = "Bearer $token" } -SkipHttpErrorCheck
  if ($direct.StatusCode -eq 401) { Write-Host '4. Your gateway token sent straight to the backend: HTTP 401, as expected' }
  else { Write-Warning "4. Your gateway token sent straight to the backend: HTTP $($direct.StatusCode) (expected 401)" }
}
