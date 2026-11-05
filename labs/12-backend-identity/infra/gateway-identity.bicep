// Attaches a user-assigned managed identity to an AI Gateway and keeps its system-assigned identity.
// A deployment sets the gateway's whole identity block, so the gateway keeps only the identities listed here. The
// template redeclares the gateway with the region and tags of the quick start's template, which
// infra/main.bicep deploys first: every "azd provision" sets the system-assigned identity there, then attaches the
// user-assigned identity again here. On a gateway you created another way, attach the identity with
// az aigateway identity assign instead, which keeps the identities the gateway already has.
targetScope = 'resourceGroup'

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways) in this resource group.')
param gatewayName string

@description('Region of the gateway.')
param location string = resourceGroup().location

@description('Tags of the gateway.')
param tags object = {}

@description('Resource ID of the user-assigned managed identity to attach.')
param identityId string

#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' = {
  name: gatewayName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {}
}

output gatewayName string = gateway.name
output principalId string = gateway.identity.principalId
