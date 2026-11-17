# The streaming alias, like lab 06's limited alias: a second alias for the same backend model, with a deliberately low
# limit of 1,000 tokens per minute for each caller identity. Clients that call the gpt-5-mini alias aren't affected.
resource "azapi_resource" "stream_alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = "${module.base.model_name}-stream"
  parent_id = module.base.workspace_id

  body = {
    properties = {
      backendModels = [
        { resourceId = module.base.model_id }
      ]
      policies = [
        {
          type       = "tokenLimit"
          count      = 1000
          period     = "minute"
          counterKey = ["identity"]
        }
      ]
    }
  }

  schema_validation_enabled = false
}
