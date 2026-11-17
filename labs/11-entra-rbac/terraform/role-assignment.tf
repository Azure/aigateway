# Grants an AI Gateway runtime role to a Microsoft Entra identity, the signed-in user by default, on all assets (the
# default workspace), the gateway, or the default alias. Runtime roles let callers invoke models and call tools. They
# don't grant gateway management. One assignment at a time: changing role_scope replaces it.
locals {
  role_ids = {
    user   = "caad7a21-134e-43f4-a550-c5ffc17e051c" # AI Gateway User: models and tools
    models = "a6b68e3d-a1f0-4c60-8678-237c050cf4ea" # AI Gateway Models User: models only
    tools  = "dce03f8d-857f-4e40-a90d-67770fa6ecd2" # AI Gateway Tools User: tools only
  }
  role_definition_id = "/subscriptions/${data.azapi_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.role_ids[var.role]}"
  principal_id       = var.principal_id != "" ? var.principal_id : data.azapi_client_config.current.object_id

  role_scope_ids = {
    workspace = module.base.workspace_id
    gateway   = module.base.gateway_id
    alias     = "${module.base.workspace_id}/aliases/${module.base.alias_name}"
  }
  role_scope_id = local.role_scope_ids[var.role_scope]
}

resource "azurerm_role_assignment" "runtime" {
  name                             = uuidv5("url", "${local.role_scope_id}/${local.principal_id}/${local.role_definition_id}")
  scope                            = local.role_scope_id
  role_definition_id               = local.role_definition_id
  principal_id                     = local.principal_id
  principal_type                   = var.principal_type
  skip_service_principal_aad_check = var.principal_type == "ServicePrincipal"
}
