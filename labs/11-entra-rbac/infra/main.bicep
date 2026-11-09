// Lab 11 with azd: "azd up" creates the resource group rg-<environment name>, the quick start's gateway, Foundry
// model, default alias, and runtime API key, then grants you an AI Gateway data-plane role so that you can call the
// model with a Microsoft Entra token instead of a key. The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and the lab\'s Foundry models are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Object ID of the identity to grant. azd sets AZURE_PRINCIPAL_ID to the signed-in user or service principal.')
param principalId string

@description('Type of that identity. azd reads it from AZURE_PRINCIPAL_TYPE, User by default.')
@allowed([ 'User', 'Group', 'ServicePrincipal' ])
param principalType string = 'User'

@description('Role to grant: user (AI Gateway User), models (AI Gateway Models User), or tools (AI Gateway Tools User). azd reads it from DATA_PLANE_ROLE.')
@allowed([ 'user', 'models', 'tools' ])
param role string = 'models'

@description('Where to grant it: the whole gateway, or only the model alias. azd reads it from DATA_PLANE_ROLE_SCOPE.')
@allowed([ 'gateway', 'alias' ])
param roleScope string = 'gateway'

var suffix = take(uniqueString(subscription().id, environmentName, location), 6)
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// The quick start's template: a gateway, a Foundry model behind the default alias, and the app-first-call key.
module base '../../quickstart/infra/resources.bicep' = {
  name: 'aigw-base'
  scope: rg
  params: {
    location: location
    tags: tags
    gatewayName: 'aigw-${suffix}'
    foundryName: 'aigw${suffix}'
  }
}

module roleAssignment 'role-assignment.bicep' = {
  name: 'aigw-role-assignment'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    principalId: principalId
    principalType: principalType
    role: role
    scope: roleScope
    scopeName: roleScope == 'alias' ? base.outputs.aliasName : ''
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = base.outputs.gatewayName
output AI_GATEWAY_ID string = base.outputs.gatewayId
output AI_GATEWAY_URL string = base.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = base.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = base.outputs.modelName
output AI_GATEWAY_MODEL string = base.outputs.aliasName
output FOUNDRY_ACCOUNT_NAME string = base.outputs.foundryName
output AI_GATEWAY_ROLE_ASSIGNMENT_ID string = roleAssignment.outputs.roleAssignmentId
output AI_GATEWAY_ROLE_SCOPE_ID string = roleAssignment.outputs.scopeId
