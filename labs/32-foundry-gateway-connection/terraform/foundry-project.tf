# The app team's side of the hub and spoke: a Foundry resource and project, each with a system-assigned managed
# identity, and the project's connection to the gateway, the same connection that Add consuming project creates on the
# gateway's page in the Foundry portal. The project's identity gets AI Gateway Models User on all of the gateway's
# assets, so the gateway accepts the project's calls, and the identity that uses the project gets Foundry User on the
# Foundry resource. Foundry shows the connected model as <connection name>/<alias>.
locals {
  app_account_name     = "aigw${local.suffix}-apps"
  connection_name      = "${module.base.gateway_name}-model-gateway"
  models_user_role_id  = "a6b68e3d-a1f0-4c60-8678-237c050cf4ea"
  foundry_user_role_id = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
  principal_id         = coalesce(var.principal_id, data.azapi_client_config.current.object_id)
}

# 1. The app team's Foundry resource. project_management_enabled turns on projects, and local auth is off.
resource "azurerm_cognitive_account" "apps" {
  name                          = local.app_account_name
  resource_group_name           = azurerm_resource_group.rg.name
  location                      = var.location
  tags                          = local.tags
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = local.app_account_name
  local_auth_enabled            = false
  project_management_enabled    = true
  public_network_access_enabled = true

  identity {
    type = "SystemAssigned"
  }
}

# 2. The project, with its own identity. The connection signs in to the gateway with it.
resource "azurerm_cognitive_account_project" "project" {
  name                 = var.project_name
  cognitive_account_id = azurerm_cognitive_account.apps.id
  location             = var.location
  tags                 = local.tags
  display_name         = var.project_name
  description          = "App team project that uses models published by the ${module.base.gateway_name} AI Gateway."

  identity {
    type = "SystemAssigned"
  }
}

# 3. The connection. Its metadata values are strings, and apimResource and models are JSON documents. azapi's schema
# doesn't know the ProjectManagedIdentity authentication type yet, so schema validation is off. azapi doesn't see a
# metadata value that disappears from the body, so changing use_responses_api replaces the connection.
resource "azapi_resource" "connection" {
  type                             = "Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01"
  name                             = local.connection_name
  parent_id                        = azurerm_cognitive_account_project.project.id
  schema_validation_enabled        = false
  replace_triggers_external_values = [var.use_responses_api]

  body = {
    properties = {
      category      = "ApiManagement"
      target        = "${module.base.gateway_url}/default/models/openai/v1"
      authType      = "ProjectManagedIdentity"
      audience      = "https://azure-api.net/aigateway"
      isSharedToAll = false
      metadata = merge(
        {
          apimResourceKind = "AiGateway"
          apimResource = jsonencode({
            id             = module.base.gateway_id
            name           = module.base.gateway_name
            gatewayUrl     = module.base.gateway_url
            location       = var.location
            subscriptionId = data.azapi_client_config.current.subscription_id
            resourceGroup  = azurerm_resource_group.rg.name
          })
          deploymentInPath    = "false"
          inferenceAPIVersion = ""
          models = jsonencode([{
            name = module.base.alias_name
            properties = {
              model = {
                name    = module.base.model_name
                version = module.base.model_version
                format  = "OpenAI"
              }
            }
          }])
        },
        var.use_responses_api ? { upstreamSurface = "responses" } : {}
      )
    }
  }
}

# 4. AI Gateway Models User for the project's identity on all of the gateway's assets: its default workspace.
resource "azurerm_role_assignment" "models_user" {
  name                             = uuidv5("url", "${module.base.workspace_id}/${azurerm_cognitive_account_project.project.id}/${local.models_user_role_id}")
  scope                            = module.base.workspace_id
  role_definition_id               = "/subscriptions/${data.azapi_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.models_user_role_id}"
  principal_id                     = azurerm_cognitive_account_project.project.identity[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

# 5. Foundry User for you, so that you can use the project's playground and agents and call it from code.
resource "azurerm_role_assignment" "foundry_user" {
  name               = uuidv5("url", "${azurerm_cognitive_account.apps.id}/${local.principal_id}/${local.foundry_user_role_id}")
  scope              = azurerm_cognitive_account.apps.id
  role_definition_id = "/subscriptions/${data.azapi_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.foundry_user_role_id}"
  principal_id       = local.principal_id
  principal_type     = var.principal_type
}
