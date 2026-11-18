# Deploys the function code in infra/hook, like azd deploy. The archive provider zips only the function's three files,
# so local files such as local.settings.json, .venv, and __pycache__ stay on your machine, as .funcignore keeps them
# out of azd deploy. Then the Azure CLI restarts the new app once (a new Flex Consumption app that reaches its storage
# through a private endpoint can fail its first code upload until it restarts) and uploads the zip with a remote
# build, which installs requirements.txt. The deployment runs again when the code or the app changes.
data "archive_file" "hook_code" {
  type        = "zip"
  output_path = "${path.module}/.terraform/hook.zip"

  dynamic "source" {
    for_each = ["function_app.py", "host.json", "requirements.txt"]
    content {
      content  = file("${path.module}/../infra/hook/${source.value}")
      filename = source.value
    }
  }
}

resource "terraform_data" "hook_code" {
  triggers_replace = [azapi_resource.hook_app.id, data.archive_file.hook_code.output_sha256]

  provisioner "local-exec" {
    command = "az functionapp restart --resource-group ${azurerm_resource_group.rg.name} --name ${azapi_resource.hook_app.name} && az functionapp deployment source config-zip --resource-group ${azurerm_resource_group.rg.name} --name ${azapi_resource.hook_app.name} --src \"${abspath(data.archive_file.hook_code.output_path)}\" --build-remote true --output none"
  }

  # The app reads its package and writes its logs with its managed identity.
  depends_on = [azurerm_role_assignment.blob_owner, azurerm_role_assignment.metrics_publisher, azapi_update_resource.hook_auth]
}
