# A token-limited alias for the quick start's model. It points at the same backend model as the default alias, but
# carries its own token limit, so a "batch" or "trial" audience gets a smaller allowance without touching the model.
resource "azapi_resource" "limited_alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = "${module.base.model_name}-limited"
  parent_id = module.base.workspace_id

  body = {
    properties = {
      backendModels = [
        { resourceId = module.base.model_id }
      ]
      policies = [
        {
          type       = "tokenLimit"
          count      = var.token_limit
          period     = var.token_limit_period
          counterKey = var.token_limit_counter_key
        }
      ]
    }
  }

  schema_validation_enabled = false
}
