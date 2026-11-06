// Publishes Foundry model deployments through the gateway: one Foundry model provider that authenticates with the
// gateway's managed identity, one backend model per deployment with model-level policies (a per-caller token limit
// and content safety), a stable client-facing alias, and optional AI Gateway Models User role assignments on that
// alias for Microsoft Entra callers.
targetScope = 'resourceGroup'

import { principal } from './types.bicep'

@description('Name of the existing gateway in this resource group.')
param gatewayName string

@description('Name of the model provider to create.')
param providerName string = 'foundry'

@description('Display name of the model provider.')
param providerDisplayName string = 'Foundry'

@description('Description of the model provider.')
param providerDescription string = ''

@description('Endpoint of the Foundry account, for example https://<foundry-account-name>.cognitiveservices.azure.com/.')
param foundryEndpoint string

@description('Resource IDs of the Foundry accounts behind the provider.')
param foundryResourceIds array

@description('Audience the gateway requests a managed identity token for when it calls Foundry.')
param foundryManagedIdentityResource string = 'https://cognitiveservices.azure.com/'

@description('Backend models: objects with armName, description, resourceId, modelName, modelVersion, tokenLimit, apiFormat, and supportedEndpoints.')
param foundryModels array

@description('Content safety threshold for every category on every backend model. The threshold is the lowest severity that is blocked.')
@allowed([
  'None'
  'Low'
  'Medium'
  'High'
])
param contentSafetySeverity string = 'Medium'

@description('Client-facing alias that apps send in the request "model" field.')
param aliasName string = 'chat'

@description('Index in foundryModels of the backend model the alias points to.')
@minValue(0)
param aliasModelIndex int = 0

@description('Microsoft Entra principals that get the AI Gateway Models User role on the alias.')
param aliasUsers principal[] = []

var normalizedFoundryEndpoint = endsWith(foundryEndpoint, '/') ? foundryEndpoint : '${foundryEndpoint}/'
var aiGatewayModelsUserRoleDefinitionId = 'a6b68e3d-a1f0-4c60-8678-237c050cf4ea'

#disable-next-line BCP081
resource aiGateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource defaultWorkspace 'Microsoft.ApiManagement/aigateways/workspaces@2025-09-01-preview' existing = {
  parent: aiGateway
  name: 'default'
}

#disable-next-line BCP081
resource foundryProvider 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: providerName
  properties: {
    kind: 'Foundry'
    displayName: providerDisplayName
    description: empty(providerDescription) ? null : providerDescription
    foundry: {
      endpoint: normalizedFoundryEndpoint
      resourceIds: foundryResourceIds
      authentication: {
        kind: 'ManagedIdentity'
        managedIdentity: {
          resource: foundryManagedIdentityResource
        }
      }
    }
  }
}

#disable-next-line BCP081
resource foundryCatalogModels 'Microsoft.ApiManagement/aigateways/workspaces/modelProviders/models@2025-09-01-preview' = [for model in foundryModels: {
  parent: foundryProvider
  name: model.armName
  properties: {
    description: model.?description ?? null
    displayName: model.modelName
    apiFormat: model.apiFormat
    supportedEndpoints: model.supportedEndpoints
    deployment: {
      resourceId: model.resourceId
      modelName: last(split(model.resourceId, '/'))
      modelVersion: model.?modelVersion ?? null
    }
    policies: [
      {
        type: 'tokenLimit'
        period: 'minute'
        count: model.?tokenLimit ?? 10000
        counterKey: [ 'identity' ]
      }
      {
        type: 'contentSafety'
        hateSeverity: contentSafetySeverity
        violenceSeverity: contentSafetySeverity
        sexualSeverity: contentSafetySeverity
        selfHarmSeverity: contentSafetySeverity
      }
    ]
  }
}]

#disable-next-line BCP081
resource alias 'Microsoft.ApiManagement/aigateways/workspaces/aliases@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: aliasName
  properties: {
    backendModels: [
      { resourceId: foundryCatalogModels[aliasModelIndex].id }
    ]
  }
}

resource aliasModelsUsers 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for user in aliasUsers: {
  scope: alias
  name: guid(alias.id, user.principalId, aiGatewayModelsUserRoleDefinitionId)
  properties: {
    principalId: user.principalId
    principalType: user.principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', aiGatewayModelsUserRoleDefinitionId)
  }
}]

output providerName string = foundryProvider.name
output modelNames array = [for (model, i) in foundryModels: foundryCatalogModels[i].name]
output aliasName string = alias.name
output aliasId string = alias.id
