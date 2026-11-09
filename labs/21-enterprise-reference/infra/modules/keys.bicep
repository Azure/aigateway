// Creates one runtime API key per app, so every app has its own policy counters, its own row in Monitoring, and a key
// you can rotate or revoke without touching the others. Templates never output key values: read a key with
// az aigateway api-key list-secrets when an app needs it.
targetScope = 'resourceGroup'

@description('Name of the existing gateway in this resource group.')
param gatewayName string

@description('One runtime API key is created per entry, named after the app, for example web-chat.')
param appNames string[] = []

#disable-next-line BCP081
resource aiGateway 'Microsoft.ApiManagement/aigateways@2025-09-01-preview' existing = {
  name: gatewayName
}

#disable-next-line BCP081
resource runtimeApiKeys 'Microsoft.ApiManagement/aigateways/apiKeys@2025-09-01-preview' = [for app in appNames: {
  parent: aiGateway
  name: app
  properties: {
    displayName: '${app} runtime key'
  }
}]

output apiKeyNames array = [for (app, i) in appNames: runtimeApiKeys[i].name]
