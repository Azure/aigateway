# The agent hooks decision service: a Python function app on the Flex Consumption plan, with:
# - App Service Authentication (Easy Auth), which accepts only Microsoft Entra tokens for the hook's app registration
#   from the gateway's managed identity, and answers 401 to every other request.
# - A private storage account (no public network access, no shared keys) that the app reaches through a virtual
#   network and a private endpoint, with its managed identity. That works in subscriptions that block public storage.
# - Application Insights with Microsoft Entra authentication, for the decision log.
# The function app and its Easy Auth settings use azapi: azurerm_function_app_flex_consumption always writes an
# AzureWebJobsStorage connection string with an account key, which a storage account without shared keys rejects.
locals {
  hook_app_name        = "func-aigw-hook-${local.suffix}"
  hook_storage_name    = "sthook${substr(sha1("${azurerm_resource_group.rg.id}/${local.hook_app_name}"), 0, 13)}"
  deployment_container = "app-package-${local.hook_app_name}"

  # Storage Blob Data Owner (host storage and deployment package) and Monitoring Metrics Publisher (Application
  # Insights with Microsoft Entra authentication).
  blob_data_owner_role_id   = "b7e6dc6d-f1e8-4753-8033-0f276bb0955b"
  metrics_publisher_role_id = "3913510d-42f4-4e42-8a64-420c390055eb"
}

resource "azurerm_virtual_network" "hook" {
  name                = "vnet-${local.hook_app_name}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  address_space       = ["10.30.0.0/16"]
  tags                = local.tags
}

# Flex Consumption joins this subnet for outbound traffic, so the app reaches the private storage account.
resource "azurerm_subnet" "app" {
  name                 = "app"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.hook.name
  address_prefixes     = ["10.30.1.0/24"]

  delegation {
    name = "flex"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "private_endpoints" {
  name                              = "private-endpoints"
  resource_group_name               = azurerm_resource_group.rg.name
  virtual_network_name              = azurerm_virtual_network.hook.name
  address_prefixes                  = ["10.30.2.0/24"]
  private_endpoint_network_policies = "Disabled"
}

resource "azurerm_storage_account" "hook" {
  name                            = local.hook_storage_name
  resource_group_name             = azurerm_resource_group.rg.name
  location                        = var.location
  account_kind                    = "StorageV2"
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false
  public_network_access           = "Disabled"
  min_tls_version                 = "TLS1_2"
  tags                            = local.tags

  network_rules {
    default_action = "Deny"
    bypass         = ["AzureServices"]
  }
}

resource "azurerm_storage_container" "packages" {
  name               = local.deployment_container
  storage_account_id = azurerm_storage_account.hook.id
}

resource "azurerm_private_dns_zone" "blob" {
  name                = "privatelink.blob.core.windows.net"
  resource_group_name = azurerm_resource_group.rg.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "hook" {
  name                 = "link-${azurerm_virtual_network.hook.name}"
  private_dns_zone_id  = azurerm_private_dns_zone.blob.id
  virtual_network_id   = azurerm_virtual_network.hook.id
  registration_enabled = false
  tags                 = local.tags
}

resource "azurerm_private_endpoint" "blob" {
  name                = "pe-${azurerm_storage_account.hook.name}-blob"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = local.tags

  private_service_connection {
    name                           = "blob"
    private_connection_resource_id = azurerm_storage_account.hook.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.blob.id]
  }
}

resource "azurerm_log_analytics_workspace" "hook" {
  name                = "log-${local.hook_app_name}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_application_insights" "hook" {
  name                         = "appi-${local.hook_app_name}"
  resource_group_name          = azurerm_resource_group.rg.name
  location                     = var.location
  application_type             = "web"
  workspace_id                 = azurerm_log_analytics_workspace.hook.id
  local_authentication_enabled = false
  tags                         = local.tags
}

resource "azurerm_service_plan" "hook" {
  name                = "plan-${local.hook_app_name}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  os_type             = "Linux"
  sku_name            = "FC1"
  tags                = local.tags
}

resource "azapi_resource" "hook_app" {
  type      = "Microsoft.Web/sites@2024-04-01"
  name      = local.hook_app_name
  parent_id = azurerm_resource_group.rg.id
  location  = var.location
  tags      = local.tags

  identity {
    type = "SystemAssigned"
  }

  body = {
    kind = "functionapp,linux"
    properties = {
      serverFarmId           = azurerm_service_plan.hook.id
      httpsOnly              = true
      virtualNetworkSubnetId = azurerm_subnet.app.id
      siteConfig = {
        minTlsVersion = "1.2"
        appSettings = [
          { name = "AzureWebJobsStorage__accountName", value = azurerm_storage_account.hook.name },
          { name = "AzureWebJobsStorage__credential", value = "managedidentity" },
          { name = "APPLICATIONINSIGHTS_CONNECTION_STRING", value = azurerm_application_insights.hook.connection_string },
          { name = "APPLICATIONINSIGHTS_AUTHENTICATION_STRING", value = "Authorization=AAD" },
          { name = "BLOCKED_TOOLS", value = var.blocked_tools },
        ]
      }
      functionAppConfig = {
        deployment = {
          storage = {
            type           = "blobContainer"
            value          = "${azurerm_storage_account.hook.primary_blob_endpoint}${azurerm_storage_container.packages.name}"
            authentication = { type = "SystemAssignedIdentity" }
          }
        }
        scaleAndConcurrency = { maximumInstanceCount = 40, instanceMemoryMB = 2048 }
        runtime             = { name = "python", version = "3.12" }
      }
    }
  }

  response_export_values = ["properties.defaultHostName"]
  # GET returns serverFarmId with .../serverfarms/..., and azurerm's plan ID has .../serverFarms/...
  ignore_casing = true

  depends_on = [azurerm_private_endpoint.blob, azurerm_private_dns_zone_virtual_network_link.hook]
}

# Easy Auth: validate the bearer token, its audience, and its caller before any function runs. An update, because a
# site's configuration can't be deleted: it goes with the app.
resource "azapi_update_resource" "hook_auth" {
  type      = "Microsoft.Web/sites/config@2024-04-01"
  name      = "authsettingsV2"
  parent_id = azapi_resource.hook_app.id

  body = {
    properties = {
      platform         = { enabled = true }
      globalValidation = { requireAuthentication = true, unauthenticatedClientAction = "Return401" }
      identityProviders = {
        azureActiveDirectory = {
          enabled = true
          registration = {
            clientId     = azuread_application.hook.client_id
            openIdIssuer = "https://sts.windows.net/${data.azapi_client_config.current.tenant_id}/v2.0"
          }
          validation = {
            allowedAudiences = [local.hook_audience, azuread_application.hook.client_id]
            defaultAuthorizationPolicy = {
              allowedPrincipals = { identities = [module.gateway.principal_id] }
            }
          }
        }
      }
      login = { tokenStore = { enabled = false } }
    }
  }
}

resource "azurerm_role_assignment" "blob_owner" {
  name                             = uuidv5("url", "${azurerm_storage_account.hook.id}/${azapi_resource.hook_app.id}/${local.blob_data_owner_role_id}")
  scope                            = azurerm_storage_account.hook.id
  role_definition_id               = "/subscriptions/${data.azapi_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.blob_data_owner_role_id}"
  principal_id                     = azapi_resource.hook_app.identity[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "metrics_publisher" {
  name                             = uuidv5("url", "${azurerm_application_insights.hook.id}/${azapi_resource.hook_app.id}/${local.metrics_publisher_role_id}")
  scope                            = azurerm_application_insights.hook.id
  role_definition_id               = "/subscriptions/${data.azapi_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.metrics_publisher_role_id}"
  principal_id                     = azapi_resource.hook_app.identity[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
