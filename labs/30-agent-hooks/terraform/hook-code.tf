# Deploys the function code in infra/hook, like azd deploy. The archive provider zips the folder, then the Azure CLI
# restarts the new app once (a new Flex Consumption app that reaches its storage through a private endpoint can fail
# its first code upload until it restarts) and uploads the zip with a remote build, which installs requirements.txt.
# The deployment runs again when the code or the app changes.
data "archive_file" "hook_code" {
  type        = "zip"
  source_dir  = "${path.module}/../infra/hook"
  output_path = "${path.module}/.terraform/hook.zip"
}

resource "terraform_data" "hook_code" {
  triggers_replace = [azapi_resource.hook_app.id, data.archive_file.hook_code.output_sha256]

  provisioner "local-exec" {
    command = "az functionapp restart --resource-group ${azurerm_resource_group.rg.name} --name ${azapi_resource.hook_app.name} && az functionapp deployment source config-zip --resource-group ${azurerm_resource_group.rg.name} --name ${azapi_resource.hook_app.name} --src \"${abspath(data.archive_file.hook_code.output_path)}\" --build-remote true --output none"
  }

  # The app reads its package and writes its logs with its managed identity.
  depends_on = [azurerm_role_assignment.blob_owner, azurerm_role_assignment.metrics_publisher, azapi_update_resource.hook_auth]
}
