// Grants the gateway's system-assigned managed identity the Foundry User role on one Foundry account, so the gateway
// can call the account's model deployments without keys. Deployed at the Foundry account's resource group.
// Same as infra/ai-gateway/foundry-user-role.bicep in the reference sample.
targetScope = 'resourceGroup'

@description('Name of the existing Foundry (Azure AI Services) account in this resource group.')
param foundryAccountName string

@description('Principal ID of the gateway\'s system-assigned managed identity.')
param gatewayPrincipalId string

@description('Resource ID of the gateway. Used to make the role assignment name deterministic.')
param gatewayResourceId string

var foundryUserRoleDefinitionId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: foundryAccountName
}

resource foundryUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundryAccount
  name: guid(foundryAccount.id, gatewayResourceId, gatewayPrincipalId, foundryUserRoleDefinitionId)
  properties: {
    principalId: gatewayPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleDefinitionId)
  }
}

output roleAssignmentName string = foundryUserRoleAssignment.name
