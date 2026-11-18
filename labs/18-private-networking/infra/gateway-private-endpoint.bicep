// Inbound private endpoint to an AI Gateway (Microsoft.ApiManagement/aigateways). This template creates:
//   - a private endpoint with the group ID "Gateway" in a subnet of the client virtual network
//   - the gateway's private DNS zone, linked to that virtual network, and a DNS zone group that adds the gateway's
//     A record to it, so clients in the network resolve the gateway's usual host name to the private IP
// The zone follows the gateway's host name: a gateway at <name>-<hash>.eastus2-01.ai.gateway.azure.com uses
// privatelink.eastus2-01.ai.gateway.azure.com, the zone that its private link resource returns in requiredZoneNames.
// Creating the endpoint needs private endpoint access for the subscription. AI Gateway approves the connection
// automatically.
// The lab's private-network.bicep calls it when gatewayPrivateEndpoint is true.

@description('Resource ID of the gateway.')
param gatewayId string

@description('Runtime host name of the gateway, without https://, for example aigw-abc123-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com.')
param gatewayHostName string

@description('Resource ID of the subnet that holds the private endpoint.')
param subnetId string

@description('Resource ID of the virtual network that the private DNS zone is linked to.')
param vnetId string

@description('Name of the private endpoint.')
param privateEndpointName string

@description('Region of the private endpoint. It must be the region of its virtual network.')
param location string = resourceGroup().location

@description('Tags applied to the private endpoint and the private DNS zone.')
param tags object = {}

// privatelink. followed by the host name without its first label, for example privatelink.eastus2-01.ai.gateway.azure.com.
var dnsZoneName = 'privatelink.${join(skip(split(gatewayHostName, '.'), 1), '.')}'

resource dnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: dnsZoneName
  location: 'global'
  tags: tags
}

resource dnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: dnsZone
  name: '${last(split(vnetId, '/'))}-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetId
    }
  }
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: privateEndpointName
  location: location
  tags: tags
  properties: {
    subnet: {
      id: subnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'gateway'
        properties: {
          privateLinkServiceId: gatewayId
          groupIds: [ 'Gateway' ]
        }
      }
    ]
  }
}

resource dnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: privateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: replace(dnsZoneName, '.', '-')
        properties: {
          privateDnsZoneId: dnsZone.id
        }
      }
    ]
  }
}

output privateEndpointName string = privateEndpoint.name
output dnsZoneName string = dnsZone.name
