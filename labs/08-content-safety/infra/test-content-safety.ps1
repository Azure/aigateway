# Sends benign test prompts through AI Gateway and prints the status of each one, so you can see
# whether the content safety policy let it through. Results vary: Azure AI Content Safety rates each
# prompt and response, and borderline themes can land on either side of a threshold.
# Requires PowerShell 7 or later.
#
# Usage:
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   $env:AI_GATEWAY_API_KEY = "..."      # never commit this value
#   ./test-content-safety.ps1 -Model <model-name> [-Prompt "your own benign prompt"]
param(
  [Parameter(Mandatory)][string]$Model,
  [string]$Prompt
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a runtime key from Access > Keys' }

$uri = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions"
$headers = @{ 'api-key' = $env:AI_GATEWAY_API_KEY }

$tests = [ordered]@{
  neutral = 'In two sentences, explain why teams put an API gateway in front of AI models.'
  fiction = 'For a historical novel, write three non-graphic sentences that describe, at a high level, two medieval armies meeting at a castle gate.'
}
if ($Prompt) { $tests['custom'] = $Prompt }

function Limit-Text([string]$Text, [int]$Length) {
  $clean = ($Text -replace '\s+', ' ').Trim()
  $clean.Substring(0, [Math]::Min($Length, $clean.Length))
}

$rows = foreach ($test in $tests.GetEnumerator()) {
  $body = @{ model = $Model; max_completion_tokens = 200; reasoning_effort = 'none'; messages = @(@{ role = 'user'; content = $test.Value }) } |
    ConvertTo-Json -Depth 5 -Compress
  $r = Invoke-WebRequest -Method Post -Uri $uri -Headers $headers -ContentType 'application/json' `
    -Body $body -TimeoutSec 120 -SkipHttpErrorCheck
  $content = if ($r.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($r.Content) } else { [string]$r.Content }
  $json = try { $content | ConvertFrom-Json } catch { $null }
  if ([int]$r.StatusCode -eq 200) {
    $finish = $json.choices[0].finish_reason
    $text = Limit-Text ([string]$json.choices[0].message.content) 70
  } else {
    $finish = '-'
    $message = if ($json.error.message) { $json.error.message } elseif ($json.message) { $json.message } else { $content }
    $text = Limit-Text ([string]$message) 110
  }
  [pscustomobject]@{ Prompt = $test.Key; Status = [int]$r.StatusCode; 'Finish reason' = $finish; 'Response or error' = $text }
}
$rows | Format-Table -AutoSize -Wrap | Out-String | Write-Host
