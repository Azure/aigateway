# Sends a few chat requests per session to one alias, each with a session-id header, and prints the backend model
# that served each request, so you can see whether every session stays on one backend model.
# Usage: ./infra/count-sessions.ps1 [-Alias chat] [-Count 4] [-Sessions alpha, bravo, none] [-SessionHeader session-id]
# The session name "none" sends no session header. Needs $env:AI_GATEWAY_URL and $env:AI_GATEWAY_API_KEY, and PowerShell 7 or later.
param(
  [string]$Alias = 'chat',
  [int]$Count = 4,
  [string[]]$Sessions = @('alpha', 'bravo', 'charlie', 'delta', 'echo', 'foxtrot', 'none'),
  [string]$SessionHeader = 'session-id',
  [double]$PauseSeconds = 0.3
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

Write-Host "Sending $Count requests per session with `"model`": `"$Alias`" and a $SessionHeader header"
Write-Host ('{0,-9} {1}' -f 'Session', 'Backend model of each request')
foreach ($s in $Sessions) {
  $headers = @{ Authorization = "Bearer $env:AI_GATEWAY_API_KEY" }
  if ($s -ne 'none') { $headers[$SessionHeader] = $s }
  $served = for ($i = 1; $i -le $Count; $i++) {
    $r = Invoke-WebRequest -Uri $url -Method Post -Headers $headers `
      -ContentType 'application/json' -Body $body -SkipHttpErrorCheck
    if ($r.StatusCode -eq 200) { ($r.Content | ConvertFrom-Json).model -replace '-\d{4}-\d{2}-\d{2}$', '' } else { "HTTP-$($r.StatusCode)" }
    Start-Sleep -Milliseconds ([int]($PauseSeconds * 1000))
  }
  $verdict = if (@($served | Select-Object -Unique).Count -eq 1) { 'stays' } else { 'moves' }
  Write-Host ('{0,-9} {1} {2}' -f $s, (($served | ForEach-Object { '{0,-13}' -f $_ }) -join ''), $verdict)
}
