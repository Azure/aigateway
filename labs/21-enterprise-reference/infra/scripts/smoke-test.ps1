# Post-deployment smoke test for the enterprise reference gateway. It proves the two runtime paths work end to end:
#   1. Model: a chat completion through the alias with an app's runtime API key (gateway -> managed identity -> Foundry).
#   2. Tools: the MCP handshake and tools/list on the federated Microsoft Learn MCP server.
# It reads the gateway host name and the key with the aigateway CLI extension, and it never prints the key.
# In GitHub Actions the key is also masked in the log. Requires PowerShell 7 or later and Azure CLI with the
# aigateway extension.
#
# Usage:
#   $env:RG = "<gateway-resource-group>"; $env:GATEWAY = "<gateway-name>"
#   ./smoke-test.ps1 [-Alias chat] [-KeyName web-chat] [-Server learn]
#
# Exits 0 when both checks pass, 1 otherwise.
param(
  [string]$Alias = 'chat',
  [string]$KeyName = 'web-chat',
  [string]$Server = 'learn'
)
$ErrorActionPreference = 'Stop'
if (-not $env:RG) { throw 'Set $env:RG to the gateway resource group' }
if (-not $env:GATEWAY) { throw 'Set $env:GATEWAY to the gateway name' }
az extension show --name aigateway -o none 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Error 'This script needs the aigateway CLI extension: irm https://aka.ms/aigateway-cli-install-ps | iex'; exit 1
}

$gatewayHost = az aigateway show -g $env:RG -n $env:GATEWAY --query properties.frontend.defaultHostname -o tsv
if (-not $gatewayHost) { Write-Error "Couldn't read the host name of gateway '$($env:GATEWAY)'."; exit 1 }
$runtimeUrl = "https://$gatewayHost"
$apiKey = az aigateway api-key list-secrets -g $env:RG --gateway-name $env:GATEWAY -n $KeyName `
  --query primaryKey -o tsv
if (-not $apiKey) { Write-Error "Couldn't read the secret of API key '$KeyName'."; exit 1 }
if ($env:GITHUB_ACTIONS -eq 'true') { Write-Host "::add-mask::$apiKey" }

Write-Host "Gateway: $runtimeUrl"

function Get-Body($Response) {
  if ($Response.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($Response.Content) } else { [string]$Response.Content }
}

# 1. Model route. New role assignments and new models can take a few minutes to start answering, so retry.
$chatUrl = "$($runtimeUrl.TrimEnd('/'))/default/models/openai/v1/chat/completions"
$chatBody = @{
  model = $Alias
  messages = @(@{ role = 'user'; content = 'Reply with exactly one word: ok' })
  max_completion_tokens = 128
} | ConvertTo-Json -Depth 5 -Compress
$chat = $null
foreach ($attempt in 1..15) {
  try {
    $chat = Invoke-WebRequest -Method Post -Uri $chatUrl -Headers @{ 'api-key' = $apiKey } `
      -ContentType 'application/json' -Body $chatBody -TimeoutSec 60 -SkipHttpErrorCheck
  } catch { $chat = $null }
  if ($chat -and $chat.StatusCode -ge 200 -and $chat.StatusCode -le 299) { break }
  if ($attempt -lt 15) {
    Write-Host "Waiting for the model route (attempt $attempt, HTTP $(if ($chat) { $chat.StatusCode } else { 'unavailable' }))..."
    Start-Sleep -Seconds 4
  }
}
if (-not $chat -or $chat.StatusCode -lt 200 -or $chat.StatusCode -gt 299) {
  Write-Host "Model  : FAILED with HTTP $(if ($chat) { $chat.StatusCode } else { 'unavailable' })"
  if ($chat) { Write-Host (Get-Body $chat) }
  exit 1
}
$completion = Get-Body $chat | ConvertFrom-Json
Write-Host ("Model  : HTTP {0}, model={1}, reply={2}, total_tokens={3}" -f $chat.StatusCode, $completion.model, `
  ($completion.choices[0].message.content -replace '\s+', ' '), $completion.usage.total_tokens)

# 2. MCP route: initialize -> notifications/initialized -> tools/list (Streamable HTTP).
$uri = "$($runtimeUrl.TrimEnd('/'))/default/toolservers/$Server/mcp"
$headers = @{ 'api-key' = $apiKey; Accept = 'application/json, text/event-stream' }

# Sends one JSON-RPC message and returns the raw HTTP response. Prints the gateway's answer and stops on non-2xx.
function Send-Mcp([hashtable]$Message, [string]$Step) {
  $r = Invoke-WebRequest -Method Post -Uri $uri -Headers $headers -ContentType 'application/json' `
    -Body ($Message | ConvertTo-Json -Depth 10 -Compress) -TimeoutSec 60 -SkipHttpErrorCheck
  if ($r.StatusCode -lt 200 -or $r.StatusCode -gt 299) {
    Write-Host "Tools  : FAILED at $Step with HTTP $($r.StatusCode)"
    Write-Host (Get-Body $r)
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
  Write-Host "Tools  : FAILED, no JSON-RPC response with id $Id in: $text"
  exit 1
}

$init = Send-Mcp @{ jsonrpc = '2.0'; id = 1; method = 'initialize'; params = @{
    protocolVersion = '2025-03-26'; capabilities = @{}; clientInfo = @{ name = 'aigateway-smoke-test'; version = '1.0' } } } 'initialize'
$initResponse = Get-RpcResponse $init 1
if (-not $initResponse.result) { Write-Host "Tools  : FAILED, initialize returned an error"; exit 1 }
$headers['MCP-Protocol-Version'] = $initResponse.result.protocolVersion
$sessionId = $init.Headers['Mcp-Session-Id'] | Select-Object -First 1
if ($sessionId) { $headers['Mcp-Session-Id'] = $sessionId }

Send-Mcp @{ jsonrpc = '2.0'; method = 'notifications/initialized' } 'notifications/initialized' | Out-Null

$listResponse = Send-Mcp @{ jsonrpc = '2.0'; id = 2; method = 'tools/list'; params = @{} } 'tools/list'
$list = Get-RpcResponse $listResponse 2
if ($list.error) { Write-Host "Tools  : FAILED, tools/list returned an error: $($list.error | ConvertTo-Json -Compress)"; exit 1 }
$tools = @($list.result.tools)
if ($tools.Count -lt 1) { Write-Host 'Tools  : FAILED, tools/list returned no tools'; exit 1 }
Write-Host "Tools  : HTTP $($listResponse.StatusCode), $($tools.Count) tools on $Server"
$tools | ForEach-Object { Write-Host "         $($_.name)" }

Write-Host 'Smoke test passed.'
