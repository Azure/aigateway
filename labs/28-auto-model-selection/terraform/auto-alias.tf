# The auto alias, which lets Model Router pick a model for each prompt. gpt-5-mini comes from the quick start's
# module and is only referenced, so its settings stay untouched. Both models share priority 0, so priority keeps
# both, then auto model selection picks one by its selector name: the model's unversioned Model Router name.
resource "azapi_resource" "auto_alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = "auto"
  parent_id = module.base.workspace_id

  body = {
    properties = {
      aliasName   = "auto"
      description = "Model Router picks ${module.base.model_name} or ${var.large_model_name} for each prompt"
      backendModels = [
        {
          resourceId        = module.base.model_id
          priority          = 0
          weight            = 1
          selectorModelName = module.base.model_name
        },
        {
          resourceId        = azapi_resource.large_model.id
          priority          = 0
          weight            = 1
          selectorModelName = var.large_model_name
        },
      ]
      selectionOrder = ["priority", "autoModelSelection"]
      autoModelSelection = {
        objective               = var.objective
        allowedRequestOverrides = var.allowed_request_overrides
      }
    }
  }

  schema_validation_enabled = false
}
