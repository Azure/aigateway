# Registers the three Microsoft Entra ID applications of the on-behalf-of chain:
#   - <base>-mcp-backend: the MCP backend's API. It exposes the delegated scope user_impersonation and is the audience
#     of the tokens that the backend accepts.
#   - <base>-token-exchange: the app that the gateway signs in as to exchange the user's token. It exposes
#     FederationApp.Access, pre-authorized for Azure AI Gateway, holds tenant-wide consent for user_impersonation, and
#     trusts the gateway identity through a federated credential, so it needs no secret.
#   - <base>-copilot-connector: the client that Microsoft 365 Copilot signs users in with. It holds tenant-wide consent
#     for AI Gateway's Data.All scope, and for openid and offline_access, so users get no consent prompt.
# terraform destroy deletes the applications, which then stay in the tenant's deleted items for 30 days: the lab's
# Clean up purges them. You add the connector's client secret when you connect Microsoft 365 Copilot, so it never
# lands in the Terraform state.
data "azuread_client_config" "current" {}

locals {
  ai_gateway_app_id = "18550318-e177-4205-a743-6816d6fcdc3f"
  graph_app_id      = "00000003-0000-0000-c000-000000000000"
  owners            = [data.azuread_client_config.current.object_id]
  backend_scope_id  = uuidv5("url", "${local.tenant_id}/${local.base_name}-mcp-backend/user_impersonation")
  exchange_scope_id = uuidv5("url", "${local.tenant_id}/${local.base_name}-token-exchange/FederationApp.Access")
  backend_scope     = "api://${azuread_application.backend.client_id}/user_impersonation"
}

# Azure AI Gateway's service principal. Before you begin creates it when it's missing: Terraform only reads it, so
# terraform destroy never deletes it.
data "azuread_service_principal" "ai_gateway" {
  client_id = local.ai_gateway_app_id
}

data "azuread_service_principal" "graph" {
  client_id = local.graph_app_id
}

resource "azuread_application" "backend" {
  display_name     = "${local.base_name}-mcp-backend"
  sign_in_audience = "AzureADMyOrg"
  owners           = local.owners

  api {
    # v2 tokens: the audience is the client ID, and the issuer is login.microsoftonline.com/<tenant>/v2.0.
    requested_access_token_version = 2

    oauth2_permission_scope {
      id                         = local.backend_scope_id
      value                      = "user_impersonation"
      type                       = "User"
      enabled                    = true
      admin_consent_display_name = "Call the MCP backend as the signed-in user"
      admin_consent_description  = "Allows the AI Gateway token exchange app to call the MCP backend on behalf of the signed-in user."
      user_consent_display_name  = "Call the MCP backend as you"
      user_consent_description   = "Allows the app to call the MCP backend on your behalf."
    }
  }

  # azuread_application_identifier_uri manages the URI, which needs the client ID.
  lifecycle {
    ignore_changes = [identifier_uris]
  }
}

resource "azuread_application_identifier_uri" "backend" {
  application_id = azuread_application.backend.id
  identifier_uri = "api://${azuread_application.backend.client_id}"
}

resource "azuread_service_principal" "backend" {
  client_id = azuread_application.backend.client_id
  owners    = local.owners
}

resource "azuread_application" "token_exchange" {
  display_name     = "${local.base_name}-token-exchange"
  sign_in_audience = "AzureADMyOrg"
  owners           = local.owners

  api {
    requested_access_token_version = 2

    oauth2_permission_scope {
      id                         = local.exchange_scope_id
      value                      = "FederationApp.Access"
      type                       = "User"
      enabled                    = true
      admin_consent_display_name = "Exchange user tokens through Azure AI Gateway"
      admin_consent_description  = "Allows Azure AI Gateway to exchange the signed-in user's token through this app."
      user_consent_display_name  = "Let Azure AI Gateway act on your behalf"
      user_consent_description   = "Allows Azure AI Gateway to call backend tools on your behalf."
    }
  }

  required_resource_access {
    resource_app_id = azuread_application.backend.client_id

    resource_access {
      id   = local.backend_scope_id
      type = "Scope"
    }
  }

  lifecycle {
    ignore_changes = [identifier_uris]
  }
}

# The gateway addresses the token exchange app as api://<client ID>. With another URI, tool calls fail with 502.
resource "azuread_application_identifier_uri" "token_exchange" {
  application_id = azuread_application.token_exchange.id
  identifier_uri = "api://${azuread_application.token_exchange.client_id}"
}

resource "azuread_service_principal" "token_exchange" {
  client_id = azuread_application.token_exchange.client_id
  owners    = local.owners
}

# The gateway identity signs in as the token exchange app. The subject is the identity's principal ID.
resource "azuread_application_federated_identity_credential" "gateway" {
  application_id = azuread_application.token_exchange.id
  display_name   = "ai-gateway"
  description    = "Azure AI Gateway user-assigned managed identity"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://login.microsoftonline.com/${local.tenant_id}/v2.0"
  subject        = azurerm_user_assigned_identity.gateway.principal_id
}

# Directory writes replicate eventually: give the new service principals time before the grants reference them.
resource "time_sleep" "entra_replication" {
  create_duration = "30s"

  depends_on = [
    azuread_service_principal.backend,
    azuread_service_principal.token_exchange,
    azuread_service_principal.connector,
  ]
}

# Azure AI Gateway can request FederationApp.Access without a consent prompt.
resource "azuread_application_pre_authorized" "ai_gateway" {
  application_id       = azuread_application.token_exchange.id
  authorized_client_id = data.azuread_service_principal.ai_gateway.client_id
  permission_ids       = [local.exchange_scope_id]
}

# Tenant-wide admin consent for the exchange: the token exchange app may call the backend as any user.
resource "azuread_service_principal_delegated_permission_grant" "token_exchange" {
  service_principal_object_id          = azuread_service_principal.token_exchange.object_id
  resource_service_principal_object_id = azuread_service_principal.backend.object_id
  claim_values                         = ["user_impersonation"]

  depends_on = [time_sleep.entra_replication]
}

resource "azuread_application" "connector" {
  display_name     = "${local.base_name}-copilot-connector"
  sign_in_audience = "AzureADMyOrg"
  owners           = local.owners

  web {
    # The redirect URI of OAuth 2.0 connectors in Microsoft 365 Copilot.
    redirect_uris = ["https://teams.microsoft.com/api/platform/v1.0/oAuthRedirect"]
  }

  required_resource_access {
    resource_app_id = local.ai_gateway_app_id

    resource_access {
      id   = data.azuread_service_principal.ai_gateway.oauth2_permission_scope_ids["Data.All"]
      type = "Scope"
    }
  }

  # openid and offline_access let Microsoft 365 Copilot sign the user in and refresh the token.
  required_resource_access {
    resource_app_id = local.graph_app_id

    resource_access {
      id   = data.azuread_service_principal.graph.oauth2_permission_scope_ids["openid"]
      type = "Scope"
    }

    resource_access {
      id   = data.azuread_service_principal.graph.oauth2_permission_scope_ids["offline_access"]
      type = "Scope"
    }
  }
}

resource "azuread_service_principal" "connector" {
  client_id = azuread_application.connector.client_id
  owners    = local.owners
}

resource "azuread_service_principal_delegated_permission_grant" "connector_gateway" {
  service_principal_object_id          = azuread_service_principal.connector.object_id
  resource_service_principal_object_id = data.azuread_service_principal.ai_gateway.object_id
  claim_values                         = ["Data.All"]

  depends_on = [time_sleep.entra_replication]
}

resource "azuread_service_principal_delegated_permission_grant" "connector_sign_in" {
  service_principal_object_id          = azuread_service_principal.connector.object_id
  resource_service_principal_object_id = data.azuread_service_principal.graph.object_id
  claim_values                         = ["openid", "offline_access"]

  depends_on = [time_sleep.entra_replication]
}
