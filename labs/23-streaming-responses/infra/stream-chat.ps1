# Streams a Chat Completions response through AI Gateway, prints the reply as it arrives, then prints how many
# server-sent events came back, how many had an empty choices array, the time to the first token, and the usage
# chunk if the stream ended with one. Invoke-RestMethod waits for the whole body, so this script reads the
# stream with HttpClient instead.
#
# Usage (PowerShell 7.4 or later):
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   $env:AI_GATEWAY_MODEL = "<model-name>"
#   $env:AI_GATEWAY_API_KEY = "..."      # never commit this value
#   ./stream-chat.ps1 [-Usage] [-Raw] [-Prompt "Your prompt"]
#
#   -Usage  sets stream_options.include_usage to true, so the stream ends with a usage chunk
#   -Raw    prints every server-sent event line instead of the reply text
param(
  [switch]$Usage,
  [switch]$Raw,
  [string]$Prompt = 'Explain in three short sentences why streaming makes chat apps feel faster.'
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
if (-not $env:AI_GATEWAY_MODEL) { throw 'Set $env:AI_GATEWAY_MODEL to the callable model alias' }
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a runtime key from Access > Keys' }

# reasoning_effort none spends the budget on the reply instead of hidden reasoning, so the first token arrives sooner.
$body = @{
  model                 = $env:AI_GATEWAY_MODEL
  stream                = $true
  max_completion_tokens = 300
  reasoning_effort      = 'none'
  messages              = @(@{ role = 'user'; content = $Prompt })
}
if ($Usage) { $body.stream_options = @{ include_usage = $true } }

$http = [System.Net.Http.HttpClient]::new()
$request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post,
  "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions")
$request.Headers.Add('api-key', $env:AI_GATEWAY_API_KEY)
$request.Content = [System.Net.Http.StringContent]::new(($body | ConvertTo-Json -Depth 5), [Text.Encoding]::UTF8, 'application/json')

$clock = [Diagnostics.Stopwatch]::StartNew()
# ResponseHeadersRead returns as soon as the headers arrive, so the body can be read while it streams.
$response = $http.SendAsync($request, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
$status = [int]$response.StatusCode
$served = if ($response.Headers.Contains('x-ms-served-model')) { $response.Headers.GetValues('x-ms-served-model') -join ', ' } else { '-' }

$events = 0; $empty = 0; $firstToken = $null; $usageChunk = $null; $other = ''
$reader = [IO.StreamReader]::new($response.Content.ReadAsStreamAsync().GetAwaiter().GetResult())
while ($null -ne ($line = $reader.ReadLine())) {
  if (-not $line.StartsWith('data: ')) { $other += $line; continue }
  if ($Raw) { Write-Host $line }
  $data = $line.Substring(6)
  if ($data -eq '[DONE]') { break }
  $chunk = $data | ConvertFrom-Json
  $events++
  if (@($chunk.choices).Count -eq 0) { $empty++ }
  if ($chunk.usage) { $usageChunk = $chunk.usage }
  foreach ($choice in @($chunk.choices)) {
    $text = $choice.delta.content
    if ($text) {
      if ($null -eq $firstToken) { $firstToken = $clock.Elapsed.TotalSeconds }
      if (-not $Raw) { Write-Host $text -NoNewline }
    }
  }
}
$reader.Dispose(); $http.Dispose()

Write-Host "`n"
if ($events -eq 0) {
  Write-Host ('{0,-19} {1}' -f 'Response body', $other)
} else {
  Write-Host ('{0,-19} {1} ({2} with an empty choices array)' -f 'Events', $events, $empty)
  Write-Host ('{0,-19} {1}' -f 'First token', $(if ($null -ne $firstToken) { $firstToken.ToString('0.00', [cultureinfo]::InvariantCulture) + ' s' } else { '-' }))
  Write-Host ('{0,-19} {1}' -f 'Usage chunk', $(if ($usageChunk) {
    "prompt $($usageChunk.prompt_tokens), completion $($usageChunk.completion_tokens), total $($usageChunk.total_tokens)"
  } else { 'none: run again with -Usage to ask for one' }))
}
Write-Host ('{0,-19} {1}' -f 'HTTP status', $status)
Write-Host ('{0,-19} {1}' -f 'Content-Type', $response.Content.Headers.ContentType)
Write-Host ('{0,-19} {1}' -f 'Served by', $served)
if ($response.Headers.RetryAfter) { Write-Host ('{0,-19} {1}' -f 'Retry-After', $response.Headers.RetryAfter.Delta.TotalSeconds) }
if ($status -ne 200) { exit 1 }
