# Sends the simple and hard prompts in prompts.json to an alias, one at a time, and shows which model served each
# one and how many tokens it used, then the totals per model. Each answer stops at 1,000 output tokens to keep the run
# short, which doesn't change which model serves it.
# Usage: ./infra/route-prompts.ps1 [-Alias auto] [-Objective Balanced|Cost|Quality]
#   -Objective: optional, sent as a per-request override that the alias must allow.
# Needs $env:AI_GATEWAY_URL and $env:AI_GATEWAY_API_KEY, and PowerShell 7 or later.
param(
  [string]$Alias = 'auto',
  [ValidateSet('', 'Balanced', 'Cost', 'Quality')]
  [string]$Objective = ''
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a gateway runtime API key' }

$url = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions"
$prompts = Get-Content -Raw (Join-Path $PSScriptRoot 'prompts.json') | ConvertFrom-Json
$headers = @{ Authorization = "Bearer $env:AI_GATEWAY_API_KEY" }

$how = if ($Objective) { "the $Objective objective" } else { "the alias's objective" }
Write-Host "Sending $($prompts.Count) prompts with `"model`": `"$Alias`" and $how"
Write-Host ('{0,3}  {1,-7} {2,-24} {3,7} {4,7}  {5}' -f '#', 'kind', 'served model', 'prompt', 'output', 'text')

$i = 0
$rows = foreach ($p in $prompts) {
  $i++
  $body = @{
    model                 = $Alias
    max_completion_tokens = 1000
    messages              = @(@{ role = 'user'; content = $p.prompt })
  }
  if ($Objective) { $body.auto_model_selection = @{ objective = $Objective } }
  $json = $body | ConvertTo-Json -Depth 5 -Compress

  # Retries a throttled (429) or busy (503) call after the time the gateway asks for.
  for ($attempt = 1; $attempt -le 5; $attempt++) {
    $r = Invoke-WebRequest -Uri $url -Method Post -Headers $headers -ContentType 'application/json' -Body $json `
      -SkipHttpErrorCheck
    if (($r.StatusCode -ne 429 -and $r.StatusCode -ne 503) -or $attempt -eq 5) { break }
    $wait = if ($r.Headers['retry-after']) { [int]"$($r.Headers['retry-after'])" } else { 10 }
    Write-Host "     HTTP $($r.StatusCode), retrying in ${wait}s"
    Start-Sleep -Seconds $wait
  }

  $reply = try { $r.Content | ConvertFrom-Json } catch { $null }
  if ($r.StatusCode -eq 200) {
    $served = if ($r.Headers['x-ms-served-model']) { "$($r.Headers['x-ms-served-model'])" } else { $reply.model }
    $in = [int]$reply.usage.prompt_tokens
    $out = [int]$reply.usage.completion_tokens
  } else {
    $served = "HTTP $($r.StatusCode) $($reply.error.code)".Trim()
    $in = 0
    $out = 0
  }
  $text = if ($p.prompt.Length -gt 50) { $p.prompt.Substring(0, 50) } else { $p.prompt }
  Write-Host ('{0,3}  {1,-7} {2,-24} {3,7} {4,7}  {5}' -f $i, $p.kind, $served, $in, $out, $text)
  [pscustomobject]@{ Model = $served; Prompt = $in; Output = $out }
}

Write-Host "`nRequests and tokens per model:"
$rows | Group-Object Model | Sort-Object Name | ForEach-Object {
  [pscustomobject]@{
    Model          = $_.Name
    Requests       = $_.Count
    'Prompt tokens' = [int]($_.Group | Measure-Object Prompt -Sum).Sum
    'Output tokens' = [int]($_.Group | Measure-Object Output -Sum).Sum
  }
} | Format-Table -AutoSize
