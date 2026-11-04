# Calls a model through AI Gateway twice, once with Chat Completions and once with the Responses API,
# and prints the HTTP status and the model's reply for each call. Requires PowerShell 7 or later.
#
# Usage:
#   $env:AI_GATEWAY_URL = "<gateway-url>"
#   $env:AI_GATEWAY_MODEL = "<model-name>"
#   $env:AI_GATEWAY_API_KEY = "..."      # never commit this value
#   ./call-model.ps1 [-Prompt "Your prompt"]
param(
  [string]$Prompt = 'Write a one-sentence status update.'
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to the gateway runtime URL, for example https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com' }
if (-not $env:AI_GATEWAY_MODEL) { throw 'Set $env:AI_GATEWAY_MODEL to the callable model alias' }
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a runtime key from Access > Keys' }

$base = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1"
$headers = @{ 'api-key' = $env:AI_GATEWAY_API_KEY }

function Invoke-Model([string]$Path, [hashtable]$Body) {
  Invoke-WebRequest -Method Post -Uri "$base$Path" -Headers $headers -ContentType 'application/json' `
    -Body ($Body | ConvertTo-Json -Depth 6) -SkipHttpErrorCheck
}

$chat = Invoke-Model '/chat/completions' @{
  model    = $env:AI_GATEWAY_MODEL
  messages = @(@{ role = 'user'; content = $Prompt })
}
$chatText = if ($chat.StatusCode -eq 200) { ($chat.Content | ConvertFrom-Json).choices[0].message.content } else { $chat.Content }

$responses = Invoke-Model '/responses' @{
  model = $env:AI_GATEWAY_MODEL
  input = $Prompt
}
$responsesText = if ($responses.StatusCode -eq 200) {
  (($responses.Content | ConvertFrom-Json).output |
    Where-Object type -eq 'message' |
    ForEach-Object { $_.content } |
    Where-Object type -eq 'output_text' |
    ForEach-Object { $_.text }) -join ''
} else { $responses.Content }

@(
  [pscustomobject]@{ Interface = 'Chat Completions'; Status = $chat.StatusCode; Reply = $chatText }
  [pscustomobject]@{ Interface = 'Responses API'; Status = $responses.StatusCode; Reply = $responsesText }
) | Format-List
