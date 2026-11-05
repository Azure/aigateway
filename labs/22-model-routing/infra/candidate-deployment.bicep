// Deploys the candidate model in an existing Foundry account, next to the primary model. main.bicep calls it after the
// quick start's template has created the account and its gpt-5-mini deployment.
targetScope = 'resourceGroup'

@description('Name of the existing Foundry (Azure AI Services) account.')
param foundryName string

@description('Model to deploy. The deployment uses the same name.')
param modelName string = 'gpt-6.1-sol'

@description('Version of the model to deploy.')
param modelVersion string = '2026-09-29'

@description('Deployment capacity in thousands of tokens per minute.')
@minValue(1)
param capacity int = 10

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

output deploymentName string = deployment.name
output foundryId string = foundry.id
