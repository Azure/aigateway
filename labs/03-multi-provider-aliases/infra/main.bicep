// Lab 03 with azd: "azd up" creates the resource group rg-<environment name>, the quick start's gateway, Foundry
// model, default alias, and runtime API key, then an Anthropic provider with two Claude models behind three
// aliases. The Anthropic key comes from ANTHROPIC_API_KEY in the azd environment and is never an output.
targetScope = 'subscription'

@description('azd environment name. The resource group is rg-<environmentName>.')
@minLength(1)
@maxLength(60)
param environmentName string

@description('Region for every resource. Pick one where AI Gateway and the lab\'s Foundry models are available. List them with az provider show --namespace Microsoft.ApiManagement (Setup guide, Find the available regions).')
@metadata({ azd: { type: 'location' } })
param location string

@secure()
@description('The Anthropic API key. azd reads it from ANTHROPIC_API_KEY.')
param anthropicApiKey string

@description('A fast model that your Anthropic key can call. azd reads it from FAST_MODEL.')
param fastModel string = 'claude-haiku-5-5'

@description('A bigger model that your Anthropic key can call. azd reads it from SMART_MODEL.')
param smartModel string = 'claude-sonnet-5-5'

@description('The backend model behind support-chat: empty for fastModel, or smartModel. azd reads it from SUPPORT_CHAT_MODEL.')
param supportChatModel string = ''

@description('Per-caller tokens per minute for support-chat. azd reads it from SUPPORT_CHAT_TOKENS_PER_MINUTE.')
@minValue(1)
param supportChatTokensPerMinute int = 20000

@description('Per-caller tokens per minute for batch-chat. azd reads it from BATCH_CHAT_TOKENS_PER_MINUTE.')
@minValue(1)
param batchChatTokensPerMinute int = 2000

var suffix = take(uniqueString(subscription().id, environmentName, location), 6)
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// The quick start's template: a gateway, a Foundry model behind the default alias, and the app-first-call key.
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

module anthropic 'anthropic-aliases.bicep' = {
  name: 'aigw-anthropic-aliases'
  scope: rg
  params: {
    gatewayName: base.outputs.gatewayName
    anthropicApiKey: anthropicApiKey
    fastModel: fastModel
    smartModel: smartModel
    supportChatModel: empty(supportChatModel) ? fastModel : supportChatModel
    supportChatTokensPerMinute: supportChatTokensPerMinute
    batchChatTokensPerMinute: batchChatTokensPerMinute
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AI_GATEWAY_NAME string = base.outputs.gatewayName
output AI_GATEWAY_ID string = base.outputs.gatewayId
output AI_GATEWAY_URL string = base.outputs.gatewayUrl
output AI_GATEWAY_PROVIDER string = base.outputs.providerName
output AI_GATEWAY_BACKEND_MODEL string = base.outputs.modelName
output AI_GATEWAY_MODEL string = base.outputs.aliasName
output FOUNDRY_ACCOUNT_NAME string = base.outputs.foundryName
output ANTHROPIC_PROVIDER string = anthropic.outputs.providerName
output ANTHROPIC_FAST_MODEL string = anthropic.outputs.fastModel
output ANTHROPIC_SMART_MODEL string = anthropic.outputs.smartModel
