// Grants an AI Gateway data-plane role to a Microsoft Entra identity at the gateway, a model alias, or an MCP server.
// Data-plane roles let callers invoke models and call tools. They don't grant gateway administration.
// The assignment name is derived from the scope, principal, and role, so redeploying the template is safe.

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways).')
param gatewayName string

@description('Object ID of the user, group, service principal, or managed identity to grant.')
param principalId string

@description('Type of the principal. Use ServicePrincipal for apps and managed identities.')
@allowed([ 'User', 'Group', 'ServicePrincipal' ])
param principalType string = 'User'

@description('Role to grant: user (AI Gateway User, models and tools), models (AI Gateway Models User), or tools (AI Gateway Tools User).')
@allowed([ 'user', 'models', 'tools' ])
param role string = 'models'

@description('Where to grant it: the whole gateway, one model alias, or one MCP server.')
@allowed([ 'gateway', 'alias', 'mcp' ])
param scope string = 'gateway'

@description('Alias name when scope is alias, or MCP server name when scope is mcp.')
param scopeName string = ''

var roleIds = {
  user: 'caad7a21-134e-43f4-a550-c5ffc17e051c'
  models: 'a6b68e3d-a1f0-4c60-8678-237c050cf4ea'
  tools: 'dce03f8d-857f-4e40-a90d-67770fa6ecd2'
}
var roleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds[role])
var childName = empty(scopeName) ? 'unused' : scopeName

#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource workspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: gateway
  name: 'default'
}

#disable-next-line BCP081
resource alias 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2025-09-01-preview' existing = {
  parent: workspace
  name: childName
}

#disable-next-line BCP081
resource toolServer 'Microsoft.ApiManagement/aigateways/workspaces/toolServers@2025-09-01-preview' existing = {
  parent: workspace
  name: childName
}

resource onGateway 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (scope == 'gateway') {
  scope: gateway
  name: guid(gateway.id, principalId, roleDefinitionId)
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: roleDefinitionId
  }
}

resource onAlias 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (scope == 'alias') {
  scope: alias
  name: guid(alias.id, principalId, roleDefinitionId)
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: roleDefinitionId
  }
}

resource onToolServer 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (scope == 'mcp') {
  scope: toolServer
  name: guid(toolServer.id, principalId, roleDefinitionId)
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: roleDefinitionId
  }
}

output roleAssignmentId string = scope == 'gateway' ? onGateway.id : (scope == 'alias' ? onAlias.id : onToolServer.id)
output scopeId string = scope == 'gateway' ? gateway.id : (scope == 'alias' ? alias.id : toolServer.id)
