// Development environment. Deploy with:
//   az deployment sub create --location eastus2 --template-file infra/main.bicep --parameters infra/main.bicepparam
// Set AZURE_PRINCIPAL_ID to your object ID (az ad signed-in-user show --query id -o tsv) to get developer access.
using './main.bicep'

param environmentName = 'aigw-dev'
param aiGatewayLocation = 'eastus2'
param principalId = readEnvironmentVariable('AZURE_PRINCIPAL_ID', '')

param modelCapacity = 50
param tokensPerMinutePerCaller = 20000
param contentSafetySeverity = 'Medium'
param aliasName = 'chat'

param appNames = [
  'web-chat'
  'batch-jobs'
]

param logRetentionInDays = 30

param tags = {
  costCenter: 'dev'
}
