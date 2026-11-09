// Provisions an Azure AI Gateway (Microsoft.ApiManagement/aigateways) with a system-assigned managed identity.
// It omits sku, so the resource provider applies its default (Standard). This follows the AI Gateway reference sample:
// https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/blob/main/infra/ai-gateway/main.bicep
// The lab's main.bicep calls it with azd, and other labs call it as a module. You can also deploy it on its own
// to an existing resource group with "az deployment group create".
targetScope = 'resourceGroup'

@description('Gateway name. It becomes the first label of the runtime host name, so use letters, numbers, and hyphens (max 24 characters).')
@minLength(1)
@maxLength(24)
param gatewayName string

@description('Region for the gateway. Pick one where AI Gateway is available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
param location string = 'eastus2'

@description('Tags applied to the gateway.')
param tags object = {}

@description('Optional subnet resource ID for outbound virtual network integration. It can only be set when the gateway is created.')
param backendSubnetId string = ''

#disable-next-line BCP081
resource aiGateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' = {
  name: gatewayName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: empty(backendSubnetId) ? {} : { backend: { subnet: { id: backendSubnetId } } }
}

output gatewayName string = aiGateway.name
output gatewayUrl string = 'https://${aiGateway.properties.frontend.defaultHostname}'
output gatewayId string = aiGateway.id
output principalId string = aiGateway.identity.principalId
