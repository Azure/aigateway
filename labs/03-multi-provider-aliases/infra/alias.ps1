# Lists, creates, retargets, and deletes AI Gateway model aliases with the `az aigateway model-alias` commands.
# Requires PowerShell 7 or later, the Azure CLI 2.75 or later (signed in), and the aigateway extension.
#
# Usage:
#   $RG = "<resource-group>"; $GATEWAY = "<gateway>"
#   ./alias.ps1 -ResourceGroup $RG -Gateway $GATEWAY list
#   ./alias.ps1 -ResourceGroup $RG -Gateway $GATEWAY show     <alias>
#   ./alias.ps1 -ResourceGroup $RG -Gateway $GATEWAY put      <alias> <provider-name> <backend-model> [tokens-per-minute]
#   ./alias.ps1 -ResourceGroup $RG -Gateway $GATEWAY retarget <alias> <provider-name> <backend-model>
#   ./alias.ps1 -ResourceGroup $RG -Gateway $GATEWAY delete   <alias>
#
# "put" creates the alias, or updates the existing one, with this backend model and these policies. With
# tokens-per-minute it sets a per-caller token limit on the alias; without it, it removes the alias policies.
# "retarget" updates only the backend model, so the alias name, description, and policies stay as they are.
param(
  [Parameter(Mandatory = $true)][string]$ResourceGroup,
  [Parameter(Mandatory = $true)][string]$Gateway,
  [Parameter(Position = 0)][ValidateSet('list', 'show', 'put', 'retarget', 'delete')][string]$Action = 'list',
  [Parameter(Position = 1)][string]$Alias,
  [Parameter(Position = 2)][string]$Provider,
  [Parameter(Position = 3)][string]$Model,
  [Parameter(Position = 4)][int]$TokensPerMinute = 0
)
$ErrorActionPreference = 'Stop'

$gatewayId = az aigateway show -g $ResourceGroup -n $Gateway --query id -o tsv
if (-not $gatewayId) { throw "Gateway '$Gateway' not found in resource group '$ResourceGroup'." }
$aliasArgs = @('-g', $ResourceGroup, '--gateway-name', $Gateway)

function Get-Aliases { @(az aigateway model-alias list @aliasArgs -o json | ConvertFrom-Json) }
function Get-AliasJson([string]$Name) { az aigateway model-alias show @aliasArgs -n $Name -o json }

# The callable alias lives in properties.aliasName and can contain "/". The resource name can't, so look
# up an existing alias by its callable name first, and otherwise derive a resource name from it.
function Get-ExistingName([string]$Name) {
  Get-Aliases | Where-Object { ($_.properties.aliasName ?? $_.name) -eq $Name } | Select-Object -First 1 -ExpandProperty name
}
function ConvertTo-ResourceName([string]$Name) { ($Name.ToLowerInvariant() -replace '[^a-z0-9_.-]+', '-').Trim('-', '.') }
function Get-ResourceName([string]$Name) {
  $found = Get-ExistingName $Name
  if ($found) { $found } else { ConvertTo-ResourceName $Name }
}

function Get-ModelId { "$gatewayId/workspaces/default/modelProviders/$Provider/models/$Model" }

function Format-Alias($Items) {
  $Items | ForEach-Object {
    $target = $_.properties.backendModels | Select-Object -First 1 -ExpandProperty resourceId
    $parts = if ($target) { $target -split '/' } else { @() }
    $policies = @($_.properties.policies | Where-Object { $_ } | ForEach-Object {
        if ($_.type -eq 'tokenLimit') { "tokenLimit $($_.count)/$($_.period)" } else { $_.type }
      })
    [pscustomobject]@{
      Alias                    = $_.properties.aliasName ?? $_.name
      'Provider/backend model' = if ($parts.Count -gt 2) { "$($parts[-3])/$($parts[-1])" } else { '-' }
      'Alias policies'         = if ($policies.Count) { $policies -join ', ' } else { '-' }
    }
  } | Format-Table -AutoSize
}

function Assert-Value([string]$Value, [string]$Message) { if (-not $Value) { throw $Message } }

switch ($Action) {
  'list' { Format-Alias (Get-Aliases) }
  'show' {
    Assert-Value $Alias 'Pass the alias.'
    Get-AliasJson (Get-ResourceName $Alias)
  }
  'put' {
    Assert-Value $Alias 'Pass the alias.'; Assert-Value $Provider 'Pass the model provider name.'; Assert-Value $Model 'Pass the backend model name.'
    $policies = @()
    if ($TokensPerMinute -gt 0) {
      $policies = @(@{ type = 'tokenLimit'; count = $TokensPerMinute; period = 'minute'; counterKey = @('identity') })
    }
    $name = Get-ResourceName $Alias
    $file = Join-Path (Get-Location) "alias-policies-$([guid]::NewGuid().ToString('N')).json"
    try {
      ConvertTo-Json -InputObject $policies -Depth 10 -Compress | Set-Content -Path $file
      az aigateway model-alias set @aliasArgs -n $name --routing-name $Alias `
        --backend-model "resource-id=$(Get-ModelId)" --policies "@$file" --only-show-errors -o none
      if ($LASTEXITCODE -ne 0) { throw "az aigateway model-alias set failed for alias '$Alias'." }
    }
    finally { Remove-Item -Path $file -ErrorAction SilentlyContinue }
    Format-Alias @(Get-AliasJson $name | ConvertFrom-Json)
  }
  'retarget' {
    Assert-Value $Alias 'Pass the alias.'; Assert-Value $Provider 'Pass the model provider name.'; Assert-Value $Model 'Pass the backend model name.'
    $name = Get-ResourceName $Alias
    az aigateway model-alias update @aliasArgs -n $name --backend-model "resource-id=$(Get-ModelId)" --only-show-errors -o none
    if ($LASTEXITCODE -ne 0) { throw "az aigateway model-alias update failed for alias '$Alias'." }
    Format-Alias @(Get-AliasJson $name | ConvertFrom-Json)
  }
  'delete' {
    Assert-Value $Alias 'Pass the alias.'
    az aigateway model-alias delete @aliasArgs -n (Get-ResourceName $Alias) --yes
    if ($LASTEXITCODE -ne 0) { throw "az aigateway model-alias delete failed for alias '$Alias'." }
    "Deleted alias $Alias"
  }
}
