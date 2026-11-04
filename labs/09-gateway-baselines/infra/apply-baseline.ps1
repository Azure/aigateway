<#
.SYNOPSIS
Applies the policy baseline in baseline-policies.json at Gateway scope (the gateway's default workspace).

.DESCRIPTION
Reads the current Gateway scope policies, replaces the entries whose type is in the baseline, keeps every
other policy, and patches the workspace. Requires the Azure CLI (az login) with the aigateway extension, and
PowerShell 7 or later.

.EXAMPLE
./apply-baseline.ps1 -ResourceGroup $RG -Gateway $GATEWAY -AllowedCidrs $env:ALLOWED_CIDRS

.EXAMPLE
./apply-baseline.ps1 -ResourceGroup $RG -Gateway $GATEWAY -AllowedCidrs $env:ALLOWED_CIDRS -DryRun

.EXAMPLE
./apply-baseline.ps1 -ResourceGroup $RG -Gateway $GATEWAY -Remove
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $ResourceGroup,
  [Parameter(Mandatory)] [string] $Gateway,
  [string] $AllowedCidrs = $env:ALLOWED_CIDRS,
  [string] $BaselineFile = (Join-Path $PSScriptRoot 'baseline-policies.json'),
  [switch] $DryRun,
  [switch] $Remove
)

$ErrorActionPreference = 'Stop'
if ($DryRun -and $Remove) { throw 'Use -DryRun or -Remove, not both.' }

$baseline = @(Get-Content -Raw -Path $BaselineFile | ConvertFrom-Json)
$types = @($baseline | ForEach-Object { $_.type })

# The file holds a placeholder address for the IP filter. Never apply it: replace it with -AllowedCidrs.
$ipFilters = @($baseline | Where-Object { $_.type -eq 'ipFilter' })
if (-not $Remove -and $ipFilters.Count -gt 0) {
  $cidrs = @(($AllowedCidrs ?? '') -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
  if ($cidrs.Count -eq 0) {
    throw 'Pass -AllowedCidrs, or set $env:ALLOWED_CIDRS, to the comma-separated CIDR ranges to allow, for example "198.51.100.7/32".'
  }
  $invalid = @($cidrs | Where-Object { $_ -notmatch '/' })
  if ($invalid.Count -gt 0) {
    throw "Use CIDR notation with a prefix length, for example $($invalid[0])/32 for a single address."
  }
  foreach ($filter in $ipFilters) { $filter.cidrRanges = $cidrs }
}

# The az aigateway policy commands set policies from flags, so to apply the whole file the script calls the
# management API with az rest.
$gatewayId = az aigateway show -g $ResourceGroup -n $Gateway --query id -o tsv
if ($LASTEXITCODE -ne 0 -or -not $gatewayId) {
  throw "Couldn't find gateway $Gateway. Sign in with az login and install the aigateway extension first."
}
$url = "https://management.azure.com$gatewayId/workspaces/default?api-version=2025-09-01-preview"

# A PATCH replaces the whole properties.policies array, so always merge with the current array.
$current = az rest --method get --url $url | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Couldn't read the gateway's default workspace." }
$policies = @($current.properties.policies | Where-Object { $_ -and $_.type -notin $types })
if (-not $Remove) { $policies += $baseline }

if ($DryRun) {
  Write-Host 'Gateway scope policies after the change (nothing was applied):'
  ConvertTo-Json -InputObject $policies -Depth 10
  return
}

if (-not $Remove -and $ipFilters.Count -gt 0) {
  Write-Host "The IP filter allows runtime calls only from: $($ipFilters[0].cidrRanges -join ', ')"
}

$body = @{ properties = @{ policies = $policies } } | ConvertTo-Json -Depth 10 -Compress
$patchFile = Join-Path (Get-Location) 'patch.json'
$body | Set-Content -Path $patchFile -Encoding utf8NoBOM
try {
  az rest --method patch --url $url --body "@$patchFile" --output none
  if ($LASTEXITCODE -ne 0) { throw 'The PATCH request failed.' }
}
finally {
  Remove-Item -Path $patchFile -ErrorAction SilentlyContinue
}

Write-Host "Gateway scope policies on ${Gateway}:"
$after = @((az rest --method get --url $url | ConvertFrom-Json).properties.policies | Where-Object { $_ })
if ($after.Count -eq 0) { Write-Host '  (none)' }
foreach ($p in $after) {
  $settings = $p | Select-Object -Property * -ExcludeProperty type | ConvertTo-Json -Depth 10 -Compress
  Write-Host "  $($p.type)  $settings"
}
