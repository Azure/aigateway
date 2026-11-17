// Sets an application's Application ID URI to api://<client ID>. An application can't reference its own client ID
// when you declare it, so entra.bicep declares it first, then this module declares it again with the same uniqueName
// once its client ID exists. The Microsoft Graph Bicep extension updates the application in place, so the properties
// that this declaration leaves out keep their values.
extension microsoftGraphV1

@description('Unique name of the existing application.')
param uniqueName string

@description('Display name of the application.')
param displayName string

@description('Client ID of the application.')
param appId string

resource application 'Microsoft.Graph/applications@v1.0' = {
  uniqueName: uniqueName
  displayName: displayName
  identifierUris: [ 'api://${appId}' ]
}

output appId string = application.appId
output identifierUri string = 'api://${appId}'
