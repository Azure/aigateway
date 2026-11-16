// Registers the decision service in Microsoft Entra ID with the Microsoft Graph Bicep extension (bicepconfig.json):
// an application whose Application ID URI is the token audience that the gateway asks for, and its service principal,
// without which Microsoft Entra ID can't issue tokens for that audience. The registration has no secret: the gateway
// signs in with its managed identity, and App Service Authentication only validates the tokens.
// Microsoft Graph objects don't belong to a resource group: delete the application when you're done
// (az ad app delete --id <client ID>). The lab's azd template does it after "azd down".
extension microsoftGraphV1

@description('Unique name of the application in the tenant. A new name creates a new application.')
param uniqueName string

@description('Display name of the application.')
param displayName string = uniqueName

resource app 'Microsoft.Graph/applications@v1.0' = {
  uniqueName: uniqueName
  displayName: displayName
  signInAudience: 'AzureADMyOrg'
  // api://<tenant ID>/<name> passes the tenant's identifier URI policy without a verified domain.
  identifierUris: [ 'api://${tenant().tenantId}/${uniqueName}' ]
}

resource principal 'Microsoft.Graph/servicePrincipals@v1.0' = {
  appId: app.appId
}

output clientId string = app.appId
output audience string = app.identifierUris[0]
