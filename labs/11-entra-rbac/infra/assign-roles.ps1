# Grants an AI Gateway data-plane role to a Microsoft Entra identity at the gateway, a model alias, or an MCP server.
#
# Usage: ./assign-roles.ps1 -Role <user|models|tools> [-Scope gateway|alias:<name>|mcp:<name>]
#                           [-PrincipalId <object-id>] [-PrincipalType User|Group|ServicePrincipal]
#   user   = AI Gateway User        (models and tools)
#   models = AI Gateway Models User (models only)
#   tools  = AI Gateway Tools User  (tools only)
# PrincipalId defaults to the signed-in user.
#
# Requires $RG and $GATEWAY (or -ResourceGroup and -GatewayName), the Azure CLI with the aigateway extension, and
# permission to create role assignments (Owner, User Access Administrator, or Role Based Access Control
# Administrator). Contributor isn't enough.
param(
  [Parameter(Mandatory)][ValidateSet('user', 'models', 'tools')][string]$Role,
  [string]$Scope = 'gateway',
  [string]$PrincipalId,
  [ValidateSet('User', 'Group', 'ServicePrincipal')][string]$PrincipalType = 'User',
  [string]$ResourceGroup = $RG,
  [string]$GatewayName = $GATEWAY
)
$ErrorActionPreference = 'Stop'
if (-not $ResourceGroup -or -not $GatewayName) { throw 'Set $RG and $GATEWAY, or pass -ResourceGroup and -GatewayName.' }

$roles = @{
  user   = @{ Id = 'caad7a21-134e-43f4-a550-c5ffc17e051c'; Name = 'AI Gateway User' }
  models = @{ Id = 'a6b68e3d-a1f0-4c60-8678-237c050cf4ea'; Name = 'AI Gateway Models User' }
  tools  = @{ Id = 'dce03f8d-857f-4e40-a90d-67770fa6ecd2'; Name = 'AI Gateway Tools User' }
}
$roleId = $roles[$Role].Id

$gatewayId = az aigateway show -g $ResourceGroup -n $GatewayName --query id -o tsv
if ($LASTEXITCODE -ne 0) { throw "Couldn't read gateway $GatewayName." }

switch -Regex ($Scope) {
  '^gateway$' { $scopeId = $gatewayId }
  '^alias:.+' {
    if ($Role -eq 'tools') { throw "AI Gateway Tools User can't be assigned on a model alias." }
    $scopeId = "$gatewayId/workspaces/default/aliases/$($Scope.Substring(6))"
  }
  '^mcp:.+' {
    if ($Role -eq 'models') { throw "AI Gateway Models User can't be assigned on an MCP server." }
    $scopeId = "$gatewayId/workspaces/default/toolServers/$($Scope.Substring(4))"
  }
  default { throw "Unknown scope '$Scope'. Use gateway, alias:<name>, or mcp:<name>." }
}

if (-not $PrincipalId) {
  $PrincipalId = az ad signed-in-user show --query id -o tsv
  $PrincipalType = 'User'
}

Write-Host "Role:      $($roles[$Role].Name) ($roleId)"
Write-Host "Principal: $PrincipalId ($PrincipalType)"
Write-Host "Scope:     $scopeId"

az role assignment create `
  --assignee-object-id $PrincipalId `
  --assignee-principal-type $PrincipalType `
  --role $roleId `
  --scope $scopeId `
  --output none
if ($LASTEXITCODE -ne 0) { throw 'Role assignment failed.' }

az role assignment list --scope $scopeId `
  --query "[?principalId=='$PrincipalId'].{Role:roleDefinitionName, PrincipalType:principalType, Scope:scope}" `
  --output table

Write-Host 'Role assignments can take several minutes to apply. Until then, calls return 403.'
