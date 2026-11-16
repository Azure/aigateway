# Sends a burst of chat requests to one alias and prints, for each one, the HTTP status, the model that served it
# (the x-ms-served-model response header), and Retry-After. Then it counts the outcomes.
# Usage: ./infra/burst.ps1 [-Alias chat-failover] [-Count 20] [-PauseSeconds 1]
# Needs $env:AI_GATEWAY_URL and $env:AI_GATEWAY_API_KEY, and PowerShell 7 or later.
param(
  [string]$Alias = 'chat-failover',
  [int]$Count = 20,
  [double]$PauseSeconds = 1
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a gateway runtime API key' }

$url = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions"
$body = @{
  model                 = $Alias
  max_completion_tokens = 16
  messages              = @(@{ role = 'user'; content = 'Reply with one word.' })
} | ConvertTo-Json -Depth 5 -Compress

# Return the first value of one response header, or '-' when the response doesn't have it
function Get-Header($response, [string]$name) {
  $value = $response.Headers[$name]
  if ($value) { @($value)[0] } else { '-' }
}

Write-Host "Sending $Count requests with `"model`": `"$Alias`""
Write-Host ('{0,-4} {1,-6} {2,-7} {3,-26} {4}' -f '#', 'Time', 'Status', 'Served by', 'Retry-After')
$start = Get-Date
$outcomes = for ($i = 1; $i -le $Count; $i++) {
  $r = Invoke-WebRequest -Uri $url -Method Post -Headers @{ Authorization = "Bearer $env:AI_GATEWAY_API_KEY" } `
    -ContentType 'application/json' -Body $body -SkipHttpErrorCheck
  $served = Get-Header $r 'x-ms-served-model'
  $elapsed = '{0}s' -f [int]((Get-Date) - $start).TotalSeconds
  Write-Host ('{0,-4} {1,-6} {2,-7} {3,-26} {4}' -f $i, $elapsed, $r.StatusCode, $served, (Get-Header $r 'retry-after'))
  if ($r.StatusCode -eq 200) { "200 $served" } else { "$($r.StatusCode)" }
  Start-Sleep -Milliseconds ([int]($PauseSeconds * 1000))
}

Write-Host "`nOutcomes:"
$outcomes | Group-Object | Sort-Object Count -Descending | Format-Table Count, Name -AutoSize
