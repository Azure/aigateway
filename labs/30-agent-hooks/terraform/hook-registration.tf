# Registers the decision service in Microsoft Entra ID: an application whose Application ID URI is the token audience
# that the gateway asks for, and its service principal, without which Microsoft Entra ID can't issue tokens for that
# audience. The registration has no secret: the gateway signs in with its managed identity, and App Service
# Authentication only validates the tokens. terraform destroy deletes the application, which then stays in the
# tenant's deleted items for 30 days: the lab's Clean up purges it.
locals {
  hook_registration_name = "aigw-lab30-hook-${local.suffix}"
  # The token audience that the gateway asks for, and that Easy Auth accepts.
  hook_audience = one(azuread_application.hook.identifier_uris)
}

resource "azuread_application" "hook" {
  display_name     = local.hook_registration_name
  sign_in_audience = "AzureADMyOrg"
  # api://<tenant ID>/<name> passes the tenant's identifier URI policy without a verified domain.
  identifier_uris = ["api://${data.azapi_client_config.current.tenant_id}/${local.hook_registration_name}"]
}

resource "azuread_service_principal" "hook" {
  client_id = azuread_application.hook.client_id
}
