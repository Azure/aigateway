// Points an AI Gateway Foundry model provider at a managed identity.
// Set identityClientId to the client ID of a user-assigned identity that's attached to the gateway and holds
// Foundry User on the account. Leave it empty to switch back to the gateway's system-assigned identity.
// This redeploys the provider that lab 02's Bicep track creates, with the same endpoint and account. Deploying
// replaces the provider's properties, so pass the display name and description you want to keep. Models and
// aliases are separate resources and stay as they are.
targetScope = 'resourceGroup'

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways) in this resource group.')
param gatewayName string

@description('Name of the existing Foundry model provider in the gateway.')
param providerName string = 'foundry-models'

@description('Resource ID of the Foundry (Azure AI Services) or Azure OpenAI account that the provider serves.')
param foundryAccountId string

@description('Client ID of a user-assigned managed identity attached to the gateway. Empty uses the system-assigned identity.')
param identityClientId string = ''

@description('Display name of the provider.')
param displayName string = 'Foundry models'

@description('Description of the provider.')
param providerDescription string = 'Managed-identity Foundry provider created by the first-model-call lab.'

var foundryAccountName = last(split(foundryAccountId, '/'))
var foundrySubscriptionId = split(foundryAccountId, '/')[2]
var foundryResourceGroup = split(foundryAccountId, '/')[4]
var cognitiveServicesAudience = 'https://cognitiveservices.azure.com/'

#disable-next-line BCP081
resource aiGateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource defaultWorkspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: aiGateway
  name: 'default'
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  scope: resourceGroup(foundrySubscriptionId, foundryResourceGroup)
  name: foundryAccountName
}

var foundryEndpoint = foundryAccount.properties.endpoint
var normalizedFoundryEndpoint = endsWith(foundryEndpoint, '/') ? foundryEndpoint : '${foundryEndpoint}/'

#disable-next-line BCP081
resource foundryProvider 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: providerName
  properties: {
    kind: 'Foundry'
    displayName: displayName
    description: providerDescription
    foundry: {
      endpoint: normalizedFoundryEndpoint
      resourceIds: [
        foundryAccountId
      ]
      authentication: {
        kind: 'ManagedIdentity'
        managedIdentity: empty(identityClientId)
          ? {
              resource: cognitiveServicesAudience
            }
          : {
              clientId: identityClientId
              resource: cognitiveServicesAudience
            }
      }
    }
  }
}

output providerName string = foundryProvider.name
output identityInUse string = empty(identityClientId) ? 'system-assigned' : identityClientId
