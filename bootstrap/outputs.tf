output "state_resource_group_name" {
  description = "Resource group of the Terraform state account."
  value       = azurerm_resource_group.tfstate.name
}

output "state_storage_account_name" {
  description = "Storage account that holds every Terraform state file."
  value       = azurerm_storage_account.tfstate.name
}

output "state_container_name" {
  description = "Blob container for Terraform state."
  value       = azurerm_storage_container.tfstate.name
}

output "state_container_id" {
  description = "ARM id of the tfstate container, the scope for blob data role assignments."
  value       = azurerm_storage_container.tfstate.id
}

output "dev_resource_group_name" {
  description = "Resource group for the dev environment, read by infra/."
  value       = azurerm_resource_group.dev.name
}

output "prod_resource_group_name" {
  description = "Resource group for the prod environment, read by infra/."
  value       = azurerm_resource_group.prod.name
}
