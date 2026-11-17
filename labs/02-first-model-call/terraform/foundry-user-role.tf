# Grants the gateway's system-assigned managed identity the Foundry User role on the Foundry account, so the
# gateway can call the account's model deployments without keys.
locals {
  foundry_user_role_id = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
}

resource "azurerm_role_assignment" "foundry_user" {
  name                             = uuidv5("url", "${azurerm_cognitive_account.foundry.id}/${module.gateway.gateway_id}/${local.foundry_user_role_id}")
  scope                            = azurerm_cognitive_account.foundry.id
  role_definition_id               = "/subscriptions/${data.azapi_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.foundry_user_role_id}"
  principal_id                     = module.gateway.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
