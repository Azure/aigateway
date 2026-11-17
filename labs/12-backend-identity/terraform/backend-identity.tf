# A user-assigned managed identity for the gateway to call its backends with, and the Foundry User role on the
# Foundry account, so that the identity can call the account's model deployments with no keys. main.tf attaches the
# identity to the gateway.
resource "azurerm_user_assigned_identity" "backends" {
  name                = var.identity_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  tags                = local.tags
}

resource "azurerm_role_assignment" "identity_foundry_user" {
  name                             = uuidv5("url", "${azurerm_cognitive_account.foundry.id}/${azurerm_user_assigned_identity.backends.id}/${local.foundry_user_role_id}")
  scope                            = azurerm_cognitive_account.foundry.id
  role_definition_id               = "/subscriptions/${data.azapi_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.foundry_user_role_id}"
  principal_id                     = azurerm_user_assigned_identity.backends.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
