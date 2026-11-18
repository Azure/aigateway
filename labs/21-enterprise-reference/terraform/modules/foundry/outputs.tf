output "name" {
  value = azurerm_cognitive_account.foundry.name
}

output "id" {
  value = azurerm_cognitive_account.foundry.id
}

output "endpoint" {
  value = azurerm_cognitive_account.foundry.endpoint
}

output "deployment_ids" {
  value = { for name, deployment in azurerm_cognitive_deployment.model : name => deployment.id }
}
