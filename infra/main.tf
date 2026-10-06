# Validation: a typo in -var-file fails at plan, before anything touches Azure.
variable "environment" {
  description = "Which environment this state file describes."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be \"dev\" or \"prod\"."
  }
}

locals {
  resource_group_name = "rg-livepoll-${var.environment}"

  tags = {
    managed-by = "terraform/app-team"
  }
}

# Data source: bootstrap owns this resource group, we only read it.
data "azurerm_resource_group" "this" {
  name = local.resource_group_name
}

# Tenant, subscription and object id of whoever runs Terraform.
data "azurerm_client_config" "current" {}

resource "azurerm_storage_account" "votes" {
  name                     = var.vote_storage_account_name
  resource_group_name      = data.azurerm_resource_group.this.name
  location                 = data.azurerm_resource_group.this.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = true # the app uses the key until Act 6

  tags = local.tags
}

resource "azurerm_storage_table" "votes" {
  name               = "votes"
  storage_account_id = azurerm_storage_account.votes.id # cross-resource reference: Terraform creates the account first
}
