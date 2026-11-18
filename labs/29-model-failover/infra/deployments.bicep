// Deploys the lab's two models in an existing Foundry account: a deliberately tiny gpt-5-mini deployment that quickly
// returns 429, and a healthy backup. main.bicep calls it after the quick start's template has created the account.
targetScope = 'resourceGroup'

@description('Name of the existing Foundry (Azure AI Services) account.')
param foundryName string

@description('Name of the tiny primary deployment.')
param primaryDeploymentName string = 'gpt-5-mini-tiny'

@description('Model of the tiny primary deployment.')
param primaryModelName string = 'gpt-5-mini'

@description('Version of the primary deployment\'s model.')
param primaryModelVersion string = '2025-08-07'

@description('Capacity of the primary, in thousands of tokens per minute. 1 makes it return 429 after a couple of requests.')
@minValue(1)
param primaryCapacity int = 1

@description('Backup model to deploy. The deployment uses the same name.')
param backupModelName string = 'gpt-6.1-sol'

@description('Version of the backup model.')
param backupModelVersion string = '2026-09-29'

@description('Capacity of the backup, in thousands of tokens per minute.')
@minValue(1)
param backupCapacity int = 10

resource foundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: foundryName
}

resource primary 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: foundry
  name: primaryDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: primaryCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: primaryModelName
      version: primaryModelVersion
    }
  }
}

// One deployment at a time: Foundry rejects a second change to an account while the first one is running.
resource backup 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: foundry
  name: backupModelName
  dependsOn: [
    primary
  ]
  sku: {
    name: 'GlobalStandard'
    capacity: backupCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: backupModelName
      version: backupModelVersion
    }
  }
}

output primaryDeploymentName string = primary.name
output primaryModelVersion string = primaryModelVersion
output backupDeploymentName string = backup.name
