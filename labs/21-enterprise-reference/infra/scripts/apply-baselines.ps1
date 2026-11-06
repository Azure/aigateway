# Applies the gateway-wide baseline policies in infra/baselines.json to an AI Gateway.
#
# Gateway-scope policies live in the policies array of the gateway's default workspace. A PATCH replaces the whole
# array, so the script reads the current array, merges the baselines into it, and writes it back:
#   - A baseline whose type already exists updates that policy in place and keeps its id, overrides, and any other
#     fields you set in the portal. Updating a costLimit this way keeps its accumulated spend.
#   - A baseline whose type doesn't exist is appended. A new costLimit gets a fresh, stable id.
#   - Policies of other types (for example ones you added in the portal) are left untouched.
# Running it twice gives the same result. The az aigateway policy commands set one policy at a time from flags, so
# to write the whole array from a file, the script calls the management API with az rest. Requires PowerShell 7 or
# later and Azure CLI.
#
# Usage:
#   $env:RG = "<gateway-resource-group>"; $env:GATEWAY = "<gateway-name>"
#   ./apply-baselines.ps1 [-Baselines ../baselines.json] [-DryRun]
param(
  [string]$Baselines = (Join-Path $PSScriptRoot '../baselines.json'),
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
if (-not $env:RG) { throw 'Set $env:RG to the gateway resource group' }
if (-not $env:GATEWAY) { throw 'Set $env:GATEWAY to the gateway name' }

$baselinePolicies = @(Get-Content -Raw -Path $Baselines | ConvertFrom-Json -AsHashtable)
$apiVersion = '2025-09-01-preview'
$sub = az account show --query id -o tsv
$url = "https://management.azure.com/subscriptions/$sub/resourceGroups/$($env:RG)/providers/Microsoft.ApiManagement/aigateways/$($env:GATEWAY)/workspaces/default?api-version=$apiVersion"

$current = az rest --method get --url $url | ConvertFrom-Json -AsHashtable
if ($LASTEXITCODE -ne 0) { throw "Couldn't read $url" }
$policies = [System.Collections.Generic.List[object]]::new()
foreach ($p in @($current.properties.policies)) { if ($p) { $policies.Add($p) } }

foreach ($b in $baselinePolicies) {
  $existing = @($policies | Where-Object { $_.type -eq $b.type })
  if ($existing.Count -gt 0) {
    foreach ($policy in $existing) {
      foreach ($key in $b.Keys) { $policy[$key] = $b[$key] }
    }
  } else {
    $new = [ordered]@{}
    foreach ($key in $b.Keys) { $new[$key] = $b[$key] }
    if ($new['type'] -eq 'costLimit' -and -not $new['id']) { $new['id'] = [guid]::NewGuid().ToString() }
    $policies.Add($new)
  }
}

Write-Host 'Gateway-scope policies after merge:'
Write-Host (ConvertTo-Json -InputObject @($policies) -Depth 10)

if ($DryRun) {
  Write-Host '-DryRun: nothing was changed.'
  return
}

$bodyFile = Join-Path ([System.IO.Path]::GetTempPath()) "aigw-baselines-$([guid]::NewGuid()).json"
try {
  @{ properties = @{ policies = @($policies) } } | ConvertTo-Json -Depth 10 -Compress | Set-Content -Path $bodyFile
  az rest --method patch --url $url --body "@$bodyFile" --output none
  if ($LASTEXITCODE -ne 0) { throw 'PATCH failed.' }
} finally {
  Remove-Item -Path $bodyFile -ErrorAction SilentlyContinue
}
Write-Host 'Applied. Current gateway-scope policy types:'
az rest --method get --url $url --query 'properties.policies[].type' -o tsv
