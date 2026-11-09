// Production environment. Same template, different values: no developer access, more capacity, longer retention,
// and access granted to Microsoft Entra groups instead of individuals. Replace the placeholder group object IDs.
//   az deployment sub create --location eastus2 --template-file infra/main.bicep --parameters infra/prod.bicepparam
using './main.bicep'

param environmentName = 'aigw-prod'
param aiGatewayLocation = 'eastus2'
param principalId = ''

param modelCapacity = 200
param tokensPerMinutePerCaller = 50000
param contentSafetySeverity = 'Medium'
param aliasName = 'chat'

param appNames = [
  'web-chat'
  'batch-jobs'
]

param modelUsers = [
  // {
  //   principalId: '<object-id-of-the-model-users-group>'
  //   principalType: 'Group'
  // }
]

param toolUsers = [
  // {
  //   principalId: '<object-id-of-the-tool-users-group>'
  //   principalType: 'Group'
  // }
]

param logRetentionInDays = 90

param tags = {
  costCenter: 'platform'
}
