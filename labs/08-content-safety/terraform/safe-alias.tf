# Publishes an alias with a content safety policy for the quick start's model. The alias points at the same backend
# model as the default alias, but screens every prompt and response it serves, so you can test thresholds without
# changing what other callers get.
resource "azapi_resource" "safe_alias" {
  type      = "Microsoft.ApiManagement/aigateways/workspaces/aliases@2026-11-01"
  name      = "${module.base.model_name}-safe"
  parent_id = module.base.workspace_id

  body = {
    properties = {
      aliasName = "${module.base.model_name}-safe"
      backendModels = [
        { resourceId = module.base.model_id }
      ]
      policies = [
        {
          type             = "contentSafety"
          hateSeverity     = var.hate_severity
          selfHarmSeverity = var.self_harm_severity
          sexualSeverity   = var.sexual_severity
          violenceSeverity = var.violence_severity
        }
      ]
    }
  }

  schema_validation_enabled = false
}
