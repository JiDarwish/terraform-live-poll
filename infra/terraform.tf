terraform {
  required_version = "~> 1.16"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.8"
    }
  }

  # Partial config: the location is shared, the key comes from envs/{env}.backend.hcl.
  # terraform init -backend-config=envs/dev.backend.hcl
  backend "azurerm" {
    resource_group_name  = "rg-livepoll-tfstate"
    storage_account_name = "stlivepolltfjd01" # must match bootstrap's local.state_storage_account_name
    container_name       = "tfstate"
    use_azuread_auth     = true
  }
}

# The subscription comes from ARM_SUBSCRIPTION_ID, never from a committed file.
provider "azurerm" {
  features {}

  # Talk to storage data planes with Entra, so Terraform keeps working when Act 6 turns key auth off.
  storage_use_azuread = true
}
