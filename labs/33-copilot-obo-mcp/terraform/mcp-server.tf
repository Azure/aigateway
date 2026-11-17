# The demo MCP backend on Azure Container Apps. An ACR Tasks run builds its image from the Git build context in
# mcp_server_source, so you don't need Docker, and terraform apply waits for the build to finish. The image tag is a
# hash of the server's files in this clone: when they change, the next apply builds the image again. Container Apps
# built-in authentication (Easy Auth) rejects every request that doesn't carry a token for the backend's application,
# requested by the token exchange app, before it reaches the container.
locals {
  mcp_server_dir = "${path.module}/../infra/mcp-server"
  image_hash     = sha1(join(",", [for f in ["Dockerfile", "requirements.txt", "server.py"] : filesha1("${local.mcp_server_dir}/${f}")]))
  image_name     = "obo-mcp-server:${substr(local.image_hash, 0, 12)}"
  acr_pull_role  = "7f951dda-4ed3-4680-a7ca-43fe172d538d"
  backend_url    = "https://${azurerm_container_app.mcp.ingress[0].fqdn}/mcp"
}

resource "azurerm_log_analytics_workspace" "mcp" {
  name                = "log-${local.base_name}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_container_registry" "mcp" {
  name                = substr(replace("acr${local.base_name}", "-", ""), 0, 50)
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.tags
}

resource "azurerm_role_assignment" "acr_pull" {
  name                             = uuidv5("url", "${azurerm_container_registry.mcp.id}/${azurerm_user_assigned_identity.mcp.principal_id}/${local.acr_pull_role}")
  scope                            = azurerm_container_registry.mcp.id
  role_definition_id               = "/subscriptions/${data.azapi_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.acr_pull_role}"
  principal_id                     = azurerm_user_assigned_identity.mcp.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "time_sleep" "acr_pull" {
  create_duration = "30s"
  depends_on      = [azurerm_role_assignment.acr_pull]
}

# The build. A run's details don't come back as they were sent, so Terraform ignores them, and a new image tag or
# build context replaces the run instead.
resource "azapi_resource" "image" {
  type      = "Microsoft.ContainerRegistry/registries/taskRuns@2019-06-01-preview"
  name      = "build-obo-mcp-server"
  parent_id = azurerm_container_registry.mcp.id
  location  = var.location

  body = {
    properties = {
      forceUpdateTag = local.image_name
      runRequest = {
        type           = "DockerBuildRequest"
        sourceLocation = var.mcp_server_source
        dockerFilePath = "Dockerfile"
        imageNames     = [local.image_name]
        isPushEnabled  = true
        platform = {
          os           = "Linux"
          architecture = "amd64"
        }
      }
    }
  }

  schema_validation_enabled        = false
  replace_triggers_external_values = [local.image_name, var.mcp_server_source]

  lifecycle {
    ignore_changes = [body]
  }
}

resource "azurerm_container_app_environment" "mcp" {
  name                       = "cae-${local.base_name}"
  resource_group_name        = azurerm_resource_group.rg.name
  location                   = var.location
  logs_destination           = "log-analytics"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.mcp.id
  tags                       = local.tags

  # Declare the Consumption profile: Azure adds it anyway, and declaring it avoids a perpetual diff.
  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
}

resource "azurerm_container_app" "mcp" {
  name                         = "ca-${local.base_name}-mcp"
  resource_group_name          = azurerm_resource_group.rg.name
  container_app_environment_id = azurerm_container_app_environment.mcp.id
  workload_profile_name        = "Consumption"
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.mcp.id]
  }

  registry {
    server   = azurerm_container_registry.mcp.login_server
    identity = azurerm_user_assigned_identity.mcp.id
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    # One replica avoids a cold start while Microsoft 365 Copilot discovers the tools.
    min_replicas = 1
    max_replicas = 3

    container {
      name   = "mcp-server"
      image  = "${azurerm_container_registry.mcp.login_server}/${local.image_name}"
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "AZURE_TENANT_ID"
        value = local.tenant_id
      }

      env {
        name  = "BACKEND_CLIENT_ID"
        value = azuread_application.backend.client_id
      }

      env {
        name  = "REQUIRED_SCOPE"
        value = "user_impersonation"
      }

      env {
        name  = "ALLOWED_CLIENT_IDS"
        value = azuread_application.token_exchange.client_id
      }

      liveness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/healthz"
      }

      readiness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/healthz"
      }
    }
  }

  depends_on = [
    azapi_resource.image,
    time_sleep.acr_pull,
  ]
}

resource "azapi_resource" "mcp_auth" {
  type      = "Microsoft.App/containerApps/authConfigs@2025-07-01"
  name      = "current"
  parent_id = azurerm_container_app.mcp.id

  body = {
    properties = {
      platform = {
        enabled = true
      }
      globalValidation = {
        unauthenticatedClientAction = "Return401"
        excludedPaths               = ["/healthz"]
      }
      httpSettings = {
        requireHttps = true
      }
      identityProviders = {
        azureActiveDirectory = {
          enabled = true
          registration = {
            clientId     = azuread_application.backend.client_id
            openIdIssuer = "https://login.microsoftonline.com/${local.tenant_id}/v2.0"
          }
          validation = {
            allowedAudiences = [azuread_application.backend.client_id]
            defaultAuthorizationPolicy = {
              allowedApplications = [azuread_application.token_exchange.client_id]
            }
          }
        }
      }
    }
  }

  schema_validation_enabled = false
}
