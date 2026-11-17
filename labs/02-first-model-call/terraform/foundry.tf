# The backend: a Microsoft Foundry (Azure AI Services) account with one gpt-5-mini deployment. Local auth is off,
# so only Entra identities, such as the gateway's managed identity, can call it. Model inference is billed.
locals {
  model_name    = "gpt-5-mini"
  model_version = "2025-08-07"
}

resource "azurerm_cognitive_account" "foundry" {
  name                          = "aigw${local.suffix}"
  resource_group_name           = azurerm_resource_group.rg.name
  location                      = var.location
  tags                          = local.tags
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = "aigw${local.suffix}"
  local_auth_enabled            = false
  public_network_access_enabled = true

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_deployment" "model" {
  name                 = local.model_name
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  sku {
    name     = "GlobalStandard"
    capacity = 10
  }

  model {
    format  = "OpenAI"
    name    = local.model_name
    version = local.model_version
  }
}
