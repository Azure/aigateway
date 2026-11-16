// Creates one runtime API key for each caller of an existing AI Gateway. main.bicep calls it after the quick
// start's template, and you can also deploy it on its own to a gateway you already have. Each key is a separate
// caller identity in metrics and logs, and the gateway generates its primary and secondary values. Key values are
// never outputs: read them with "az aigateway api-key list-secrets", which needs the
// Microsoft.ApiManagement/aigateways/apiKeys/listSecrets/action permission.

@description('Name of the existing AI Gateway (Microsoft.ApiManagement/aigateways).')
param gatewayName string

@description('Key names, one for each caller. Names must be unique, ignoring case.')
param apiKeyNames array = [
  'app-dev'
  'support-bot'
  'old-notebook'
]

#disable-next-line BCP081
resource gateway 'Microsoft.ApiManagement/aigateways@2026-11-01' existing = {
  name: gatewayName
}

// Redeploying keeps each key's values: rotation and revocation are operations, not part of the template.
#disable-next-line BCP081
resource apiKeys 'Microsoft.ApiManagement/aigateways/apiKeys@2026-11-01' = [for name in apiKeyNames: {
  parent: gateway
  name: name
  properties: {
    // Keep the display name the same as the key's name, which the CLI and the scripts use.
    displayName: name
  }
}]

output apiKeyNames array = [for (name, i) in apiKeyNames: apiKeys[i].name]
output apiKeyIds array = [for (name, i) in apiKeyNames: apiKeys[i].id]
