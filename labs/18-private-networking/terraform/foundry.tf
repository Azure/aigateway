# A dedicated Microsoft Foundry (Azure AI Services) account with one gpt-5-mini deployment for this lab, so turning
# off its public access doesn't block the Foundry resource that the earlier labs use. Local auth is off: only
# Microsoft Entra identities, such as the gateway's managed identity, can call it. Model inference is billed.
resource "azurerm_cognitive_account" "foundry" {
  name                          = "aigw${local.suffix}"
  resource_group_name           = azurerm_resource_group.rg.name
  location                      = var.location
  tags                          = local.tags
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = "aigw${local.suffix}"
  local_auth_enabled            = false
  public_network_access_enabled = var.foundry_public_network_access == "Enabled"

  identity {
    type = "SystemAssigned"
  }

  network_acls {
    default_action = "Allow"
  }
}

resource "azurerm_cognitive_deployment" "model" {
  name                 = "gpt-5-mini"
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  sku {
    name     = "GlobalStandard"
    capacity = 10
  }

  model {
    format  = "OpenAI"
    name    = "gpt-5-mini"
    version = "2025-08-07"
  }
}
