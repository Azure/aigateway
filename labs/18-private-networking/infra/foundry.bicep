// A dedicated Microsoft Foundry (Azure AI Services) account with one gpt-5-mini deployment for this lab, so turning
// off its public access doesn't block the Foundry resource that the earlier labs use. Local auth is off: only
// Microsoft Entra identities, such as the gateway's managed identity, can call it. Model inference is billed.
// The lab's main.bicep calls it with azd, first with publicNetworkAccess 'Enabled', then 'Disabled' once the
// private endpoint is in place.
targetScope = 'resourceGroup'

@description('Foundry account name. It is also used as the custom subdomain, so it must be globally unique.')
@minLength(2)
@maxLength(64)
param accountName string

@description('Region for the Foundry account. The model and SKU must be available in this region.')
param location string = resourceGroup().location

@description('Name of the model deployment that the gateway publishes.')
param deploymentName string = 'gpt-5-mini'

@description('Model to deploy.')
param modelName string = 'gpt-5-mini'

@description('Model version to deploy.')
param modelVersion string = '2025-08-07'

@description('Deployment SKU.')
param skuName string = 'GlobalStandard'

@description('Deployment capacity in thousands of tokens per minute.')
@minValue(1)
param capacity int = 10

@description('Public network access. Set it to Disabled after the private endpoint exists, so that only callers in the virtual network, such as the gateway, reach the account.')
@allowed([
  'Enabled'
  'Disabled'
])
param publicNetworkAccess string = 'Enabled'

@description('Tags applied to the account.')
param tags object = {}

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: false
    customSubDomainName: toLower(accountName)
    disableLocalAuth: true
    networkAcls: {
      defaultAction: 'Allow'
      virtualNetworkRules: []
      ipRules: []
    }
    publicNetworkAccess: publicNetworkAccess
  }
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: account
  name: deploymentName
  sku: {
    name: skuName
    capacity: capacity
  }
  properties: {
    model: {
      name: modelName
      format: 'OpenAI'
      version: modelVersion
    }
  }
}

output accountId string = account.id
output accountName string = account.name
output endpoint string = account.properties.endpoint
output deploymentName string = deployment.name
