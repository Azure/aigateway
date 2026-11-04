# Sends chat requests to one alias and counts which backend model answered each one.
# Usage: ./infra/count-models.ps1 [-Alias chat] [-Count 20] [-PauseSeconds 0.5]
# Needs $env:AI_GATEWAY_URL and $env:AI_GATEWAY_API_KEY, and PowerShell 7 or later.
param(
  [string]$Alias = 'chat',
  [int]$Count = 20,
  [double]$PauseSeconds = 0.5
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

Write-Host "Sending $Count requests with `"model`": `"$Alias`""
$served = for ($i = 1; $i -le $Count; $i++) {
  $r = Invoke-WebRequest -Uri $url -Method Post -Headers @{ 'api-key' = $env:AI_GATEWAY_API_KEY } `
    -ContentType 'application/json' -Body $body -SkipHttpErrorCheck
  $name = if ($r.StatusCode -eq 200) { ($r.Content | ConvertFrom-Json).model } else {
    $code = try { ($r.Content | ConvertFrom-Json).error.code } catch { '' }
    "HTTP $($r.StatusCode) $code".Trim()
  }
  Write-Host ('{0,3}  {1}' -f $i, $name)
  $name
  Start-Sleep -Milliseconds ([int]($PauseSeconds * 1000))
}

Write-Host "`nRequests per backend model:"
$served | Group-Object | Sort-Object Count -Descending | Format-Table Count, Name -AutoSize
