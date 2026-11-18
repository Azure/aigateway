// The protected MCP backend of lab 33, in one resource group: two user-assigned managed identities, the three
// Microsoft Entra ID app registrations of the on-behalf-of chain (entra.bicep), and the demo MCP server on Azure
// Container Apps (mcp-server.bicep). It doesn't touch the gateway: you attach the gateway identity and register the
// MCP server yourself, or main.bicep does it for you with azd. Deploy it on its own with:
//   az deployment group create --resource-group <resource group> --template-file infra/backend.bicep
targetScope = 'resourceGroup'

@description('Prefix of every resource and app registration name. The default is unique to the resource group.')
@minLength(3)
@maxLength(20)
param baseName string = 'aigw-lab33-${take(uniqueString(resourceGroup().id), 6)}'

@description('Region of the resources.')
param location string = resourceGroup().location

@description('Tags of the Azure resources.')
param tags object = {}

@description('Git build context of the MCP server image: <repository>.git#<branch>:<folder>.')
param mcpServerSource string = 'https://github.com/Azure/aigateway.git#main:labs/33-copilot-obo-mcp/infra/mcp-server'

@description('Image tag. The default builds the image again on every deployment.')
param imageTag string = utcNow('yyyyMMddHHmmss')

// The gateway signs in as the token exchange app with this identity.
resource gatewayIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${baseName}-gateway'
  location: location
  tags: tags
}

// The container app pulls its image with this identity.
resource mcpIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${baseName}-mcp'
  location: location
  tags: tags
}

module entra 'entra.bicep' = {
  name: 'aigw-obo-entra'
  params: {
    baseName: baseName
    gatewayIdentityPrincipalId: gatewayIdentity.properties.principalId
  }
}

module mcpServer 'mcp-server.bicep' = {
  name: 'aigw-obo-mcp-server'
  params: {
    baseName: baseName
    location: location
    tags: tags
    identityId: mcpIdentity.id
    identityPrincipalId: mcpIdentity.properties.principalId
    backendAppId: entra.outputs.backendAppId
    tokenExchangeAppId: entra.outputs.tokenExchangeAppId
    sourceLocation: mcpServerSource
    imageTag: imageTag
  }
}

output baseName string = baseName
output gatewayIdentityId string = gatewayIdentity.id
output gatewayIdentityClientId string = gatewayIdentity.properties.clientId
output backendAppId string = entra.outputs.backendAppId
output backendScope string = entra.outputs.backendScope
output tokenExchangeAppId string = entra.outputs.tokenExchangeAppId
output connectorAppId string = entra.outputs.connectorAppId
output backendUrl string = mcpServer.outputs.mcpUrl
output containerAppName string = mcpServer.outputs.containerAppName
