# The Foundry model provider. It calls the account with a managed identity: the gateway's system-assigned identity,
# or your user-assigned identity when use_user_assigned_identity is true, which adds its clientId.
resource "azapi_resource" "provider" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/modelProviders@2026-11-01"
  name      = "foundry-models"
  parent_id = local.workspace_id

  body = {
    properties = {
      modelProviderType = "Foundry"
      displayName       = "Foundry models"
      foundry = {
        endpoint = {
          url = "https://${local.foundry_name}.cognitiveservices.azure.com/"
        }
        resourceIds = [azurerm_cognitive_account.foundry.id]
      }
      authentication = {
        managedIdentity = {
          resource = "https://cognitiveservices.azure.com/"
          # A null clientId is left out of the request, so the provider uses the system-assigned identity. Unlike a
          # missing key, null makes the plan show the change when you switch back.
          clientId = var.use_user_assigned_identity ? azurerm_user_assigned_identity.backends.client_id : null
        }
      }
    }
  }

  schema_validation_enabled = false
  depends_on = [
    azurerm_role_assignment.gateway_foundry_user,
    azurerm_role_assignment.identity_foundry_user,
  ]
}
