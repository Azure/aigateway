// Deploys text-embedding-3-small in an existing Foundry account, next to the chat model. main.bicep calls it after the
// quick start's template has created the account and its gpt-5-mini deployment.
targetScope = 'resourceGroup'

@description('Name of the existing Foundry (Azure AI Services) account.')
param foundryName string

@description('Embedding model to deploy. The deployment uses the same name.')
param modelName string = 'text-embedding-3-small'

@description('Version of the embedding model to deploy.')
param modelVersion string = '1'

@description('Deployment capacity in thousands of tokens per minute.')
@minValue(1)
param capacity int = 20

resource foundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: foundryName
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: foundry
  name: modelName
  sku: {
    name: 'GlobalStandard'
    capacity: capacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
  }
}

output deploymentId string = deployment.id
output deploymentName string = deployment.name
output modelVersion string = modelVersion
