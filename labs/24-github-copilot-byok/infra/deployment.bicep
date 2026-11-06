// Adds one model deployment to an existing Foundry (Azure AI Services) account.
targetScope = 'resourceGroup'

param accountName string
param modelName string
param modelVersion string
param skuName string
param capacity int

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: account
  name: modelName
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

output deploymentName string = deployment.name
