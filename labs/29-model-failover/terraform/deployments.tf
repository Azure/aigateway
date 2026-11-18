# The lab's two models, in the quick start's Foundry account: a deliberately tiny gpt-5-mini deployment that quickly
# returns 429, and a healthy backup. The gateway's Foundry User role on the account already covers them.
locals {
  primary_deployment_name = "gpt-5-mini-tiny"
  primary_model_name      = "gpt-5-mini"
  primary_model_version   = "2025-08-07"
}

# Capacity 1, the smallest there is: 1,000 tokens and 1 request per minute, so it returns 429 after a couple of
# requests. Foundry rejects a second change to an account while the first one is running, so the deployments wait
# for the quick start's module, and then for each other.
resource "azurerm_cognitive_deployment" "primary" {
  name                 = local.primary_deployment_name
  cognitive_account_id = module.base.foundry_id

  sku {
    name     = "GlobalStandard"
    capacity = 1
  }

  model {
    format  = "OpenAI"
    name    = local.primary_model_name
    version = local.primary_model_version
  }

  depends_on = [module.base]
}

# The backup, with 10,000 tokens and 10 requests per minute. The deployment uses the model's name.
resource "azurerm_cognitive_deployment" "backup" {
  name                 = var.backup_model_name
  cognitive_account_id = module.base.foundry_id

  sku {
    name     = "GlobalStandard"
    capacity = 10
  }

  model {
    format  = "OpenAI"
    name    = var.backup_model_name
    version = var.backup_model_version
  }

  depends_on = [azurerm_cognitive_deployment.primary]
}
