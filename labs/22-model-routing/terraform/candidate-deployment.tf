# The candidate deployment, in the same Foundry account as gpt-5-mini. The gateway's Foundry User role on the
# account already covers it.
resource "azurerm_cognitive_deployment" "candidate" {
  name                 = var.candidate_model_name
  cognitive_account_id = module.base.foundry_id

  sku {
    name     = "GlobalStandard"
    capacity = 10
  }

  model {
    format  = "OpenAI"
    name    = var.candidate_model_name
    version = var.candidate_model_version
  }
}
