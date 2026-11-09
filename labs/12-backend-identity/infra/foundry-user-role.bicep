// Grants a managed identity the Foundry User role on a Foundry (Azure AI Services) or Azure OpenAI account, so
// AI Gateway can call the account's model deployments with that identity and no keys.
// Adapted from lab 02's foundry-user-role.bicep, which grants the same role to the gateway's system identity.
targetScope = 'resourceGroup'

@description('Name of the Foundry (Azure AI Services) or Azure OpenAI account.')
param foundryAccountName string

@description('Principal (object) ID of the managed identity that receives the role.')
param principalId string

var foundryUserRoleDefinitionId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: foundryAccountName
}

resource foundryUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundryAccount
  name: guid(foundryAccount.id, principalId, foundryUserRoleDefinitionId)
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleDefinitionId)
  }
}

output roleAssignmentName string = foundryUserRoleAssignment.name
