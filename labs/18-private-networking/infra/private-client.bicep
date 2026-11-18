// A throwaway client inside the virtual network, to test the gateway's inbound private endpoint: an Azure Container
// Instances container group in a subnet delegated to Microsoft.ContainerInstance/containerGroups. It resolves the
// gateway's host name, calls the model alias once through the gateway, prints the IP it reached and the HTTP status,
// and stops. Run it again with "az container start", and read its output with "az container logs".
// The API key is a secure environment variable: it never shows in the deployment or in the container's properties.
// Every track of lab 18 deploys it with "az deployment group create". Container Instances bills only while it runs.

@description('Name of the container group.')
param name string = 'aci-private-client'

@description('Region of the container group. It must be the region of its virtual network.')
param location string = resourceGroup().location

@description('Resource ID of a subnet delegated to Microsoft.ContainerInstance/containerGroups.')
param subnetId string

@description('Runtime host name of the gateway, without https://.')
param gatewayHostName string

@description('Model alias to call.')
param model string

@description('Runtime API key of the gateway.')
@secure()
param apiKey string

@description('Tags applied to the container group.')
param tags object = {}

// Resolve the host, then call the alias and print the HTTP status and the IP that answered.
var probe = '''
echo "DNS: $(getent hosts "$AI_GATEWAY_HOST")"
curl -sS -o /dev/null -w 'HTTP %{http_code} from %{remote_ip}\n' \
  "https://$AI_GATEWAY_HOST/default/models/openai/v1/chat/completions" \
  -H "Authorization: Bearer $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly one word: ok\"}],\"max_completion_tokens\":128}"
'''

resource client 'Microsoft.ContainerInstance/containerGroups@2023-05-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    osType: 'Linux'
    restartPolicy: 'Never'
    subnetIds: [
      {
        id: subnetId
      }
    ]
    containers: [
      {
        name: 'probe'
        properties: {
          image: 'mcr.microsoft.com/azure-cli:latest'
          command: [ '/bin/bash', '-c', probe ]
          environmentVariables: [
            {
              name: 'AI_GATEWAY_HOST'
              value: gatewayHostName
            }
            {
              name: 'AI_GATEWAY_MODEL'
              value: model
            }
            {
              name: 'AI_GATEWAY_API_KEY'
              secureValue: apiKey
            }
          ]
          resources: {
            requests: {
              cpu: 1
              memoryInGB: 1
            }
          }
        }
      }
    ]
  }
}

output name string = client.name
