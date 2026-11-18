// Lab 29 with azd: "azd up" creates the resource group rg-<environment name>, the quick start's gateway, Foundry
// model, default alias, and runtime API key. Then it adds a tiny primary deployment and a backup deployment in the same
// Foundry account, and publishes the chat-failover alias, which prefers the primary and, with FAILOVER=on, fails over
// to the backup when the primary returns 429. The runtime API key is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and the lab\'s Foundry models are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@description('Backup model to deploy in Foundry. azd reads it from BACKUP_MODEL.')
param backupModelName string = 'gpt-6.1-sol'

@description('Version of the backup model. azd reads it from BACKUP_MODEL_VERSION.')
param backupModelVersion string = '2026-09-29'

@description('off: the alias only prefers the primary by priority. on: it also fails over on 429. azd reads it from FAILOVER.')
@allowed([
  'off'
  'on'
])
param failover string = 'off'

@description('How long a throttled backend stays out of the alias, as an ISO 8601 duration up to P1D. Empty: only for the current request. azd reads it from FAILOVER_EXCLUDE_FOR.')
param excludeFor string = 'PT30S'

var suffix = take(uniqueString(subscription().id, environmentName, location), 6)
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// The quick start's template: a gateway, gpt-5-mini behind the default alias, and the app-first-call key.
module base '../../quickstart/infra/resources.bicep' = {
  name: 'aigw-base'
  scope: rg
  params: {
    location: location
    tags: tags
    gatewayName: 'aigw-${suffix}'
    foundryName: 'aigw${suffix}'
  }
}

// The tiny primary and the backup, in the same Foundry account. The gateway's Foundry User role already covers them.
module deployments 'deployments.bicep' = {
  name: 'aigw-failover-deployments'
  scope: rg
  params: {
    foundryName: base.outputs.foundryName
    backupModelName: backupModelName
    backupModelVersion: backupModelVersion
  }
}

module alias 'failover-alias.bicep' = {
  name: 'aigw-failover-alias'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    providerName: base.outputs.providerName
    foundryAccountId: base.outputs.foundryId
    primaryDeploymentName: deployments.outputs.primaryDeploymentName
    primaryModelVersion: deployments.outputs.primaryModelVersion
    backupDeploymentName: deployments.outputs.backupDeploymentName
    backupModelVersion: backupModelVersion
    aliasName: 'chat-failover'
    failover: failover
    excludeFor: excludeFor
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = base.outputs.gatewayName
output AI_GATEWAY_ID string = base.outputs.gatewayId
output AI_GATEWAY_URL string = base.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = base.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = alias.outputs.primaryModelName
output AI_GATEWAY_BACKUP_MODEL string = alias.outputs.backupModelName
output AI_GATEWAY_MODEL string = alias.outputs.aliasName
output FOUNDRY_ACCOUNT_NAME string = base.outputs.foundryName
output FOUNDRY_ACCOUNT_ID string = base.outputs.foundryId
