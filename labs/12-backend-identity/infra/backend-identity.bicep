// Creates a user-assigned managed identity for AI Gateway to call its backends with, and grants that identity
// the Foundry User role on an existing Foundry (Azure AI Services) or Azure OpenAI account.
// Attaching the identity to the gateway is a separate step, with az aigateway identity assign or
// gateway-identity.bicep: declaring the gateway here would redeploy the whole gateway resource. Point a model
// provider at the identity afterwards with provider.bicep or az aigateway model-provider update.
// infra/main.bicep calls this template, gateway-identity.bicep, and provider.bicep for azd.
targetScope = 'resourceGroup'

@description('Name of the user-assigned managed identity to create.')
param identityName string = 'id-aigateway-backends'

@description('Region of the identity. Defaults to the resource group region.')
param location string = resourceGroup().location

@description('Resource ID of the Foundry (Azure AI Services) or Azure OpenAI account. It can be in another resource group or subscription.')
param foundryAccountId string

var foundryAccountName = last(split(foundryAccountId, '/'))
var foundrySubscriptionId = split(foundryAccountId, '/')[2]
var foundryResourceGroup = split(foundryAccountId, '/')[4]

resource backendIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

module foundryUserRole './foundry-user-role.bicep' = {
  name: take('foundry-user-${uniqueString(backendIdentity.id, foundryAccountId)}', 64)
  scope: resourceGroup(foundrySubscriptionId, foundryResourceGroup)
  params: {
    foundryAccountName: foundryAccountName
    principalId: backendIdentity.properties.principalId
  }
}

output identityId string = backendIdentity.id
output clientId string = backendIdentity.properties.clientId
output principalId string = backendIdentity.properties.principalId
output foundryUserRoleAssignmentName string = foundryUserRole.outputs.roleAssignmentName
