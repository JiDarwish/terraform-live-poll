terraform {
  required_version = "~> 1.16"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.8"
    }
  }

  # This root stores its own state in the container it creates.
  # The very first run uses a gitignored local_override.tf with a local backend,
  # then `terraform init -migrate-state` moves the state here.
  # See "Bootstrap (run once)" in README.md.
  backend "azurerm" {
    resource_group_name  = "rg-livepoll-tfstate"
    storage_account_name = "stlivepolltfjd01" # must match local.state_storage_account_name
    container_name       = "tfstate"
    key                  = "bootstrap.tfstate"
    use_azuread_auth     = true
  }
}

provider "azurerm" {
  features {}

  subscription_id = var.subscription_id

  # Shared-key auth is off on the state account, so talk to blob storage with Entra.
  storage_use_azuread = true
}
