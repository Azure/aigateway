// The AI Gateway itself: a Microsoft.ApiManagement/aigateways resource in the Standard SKU with a system-assigned
// managed identity, the companion connector gateway (created after it, as in the reference sample), and the Foundry
// User role for the gateway identity on every Foundry account it calls.
targetScope = 'resourceGroup'

@description('Location of the gateway. Pick one where AI Gateway is available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
param location string

@description('Gateway name, max 24 characters. Its first 10 characters start the runtime host name.')
@maxLength(24)
param gatewayName string

@description('Tags applied to the gateway.')
param tags object = {}

@description('Optional subnet resource ID for outbound virtual network integration. It can only be set when the gateway is created.')
param backendSubnetId string = ''

@description('Resource IDs of the Foundry accounts the gateway calls with its managed identity.')
param foundryResourceIds array = []

#disable-next-line BCP081
resource aiGateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' = {
  name: gatewayName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'Standard'
  }
  properties: empty(backendSubnetId) ? {} : { backend: { subnet: { id: backendSubnetId } } }
}

#disable-next-line BCP081
resource connectorNamespace 'Microsoft.Web/connectorGateways@2026-05-01-preview' = {
  name: gatewayName
  location: location
  tags: tags
  properties: {}
  dependsOn: [
    aiGateway
  ]
}

module foundryUserRoleAssignments './foundry-user-role.bicep' = [for (foundryResourceId, i) in foundryResourceIds: {
  name: 'foundry-rbac-${i}-${uniqueString(foundryResourceId, gatewayName)}'
  scope: resourceGroup(split(foundryResourceId, '/')[2], split(foundryResourceId, '/')[4])
  params: {
    foundryAccountName: last(split(foundryResourceId, '/'))
    gatewayPrincipalId: aiGateway.identity.principalId
    gatewayResourceId: aiGateway.id
  }
}]

output gatewayName string = aiGateway.name
output gatewayId string = aiGateway.id
output gatewayUrl string = 'https://${aiGateway.properties.frontend.defaultHostname}'
output runtimeHostname string = aiGateway.properties.frontend.defaultHostname
output gatewayPrincipalId string = aiGateway.identity.principalId
output connectorNamespaceId string = connectorNamespace.id
output foundryUserRoleAssignmentNames array = [for (foundryResourceId, i) in foundryResourceIds: foundryUserRoleAssignments[i].outputs.roleAssignmentName]
