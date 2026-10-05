locals {
  # Fixed, globally unique name. The backend block can't use variables.
  state_storage_account_name = "stlivepolltfjd01" # must match bootstrap/terraform.tf

  tags = {
    managed-by = "terraform/bootstrap"
  }
}

resource "azurerm_resource_group" "tfstate" {
  name     = "rg-livepoll-tfstate"
  location = var.location
  tags     = local.tags
}

# Owned here; infra/ reads them with a data source.
resource "azurerm_resource_group" "dev" {
  name     = "rg-livepoll-dev"
  location = var.location
  tags     = local.tags
}

resource "azurerm_resource_group" "prod" {
  name     = "rg-livepoll-prod"
  location = var.location
  tags     = local.tags
}

resource "azurerm_storage_account" "tfstate" {
  name                     = local.state_storage_account_name
  resource_group_name      = azurerm_resource_group.tfstate.name
  location                 = azurerm_resource_group.tfstate.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  min_tls_version                 = "TLS1_2" # no legacy TLS
  shared_access_key_enabled       = false    # Entra only: no account keys, no SAS
  allow_nested_items_to_be_public = false    # no anonymous blob access
  default_to_oauth_authentication = true     # the portal browses with Entra, not the key

  blob_properties {
    versioning_enabled = true # every state write keeps the previous version

    delete_retention_policy {
      days = 7 # blob soft delete
    }

    container_delete_retention_policy {
      days = 7 # container soft delete
    }
  }

  tags = local.tags

  # reset.sh applies this root unattended. Losing this account loses every state file.
  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_storage_container" "tfstate" {
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.tfstate.id # via ARM, works with key auth off
  container_access_type = "private"

  lifecycle {
    prevent_destroy = true
  }
}

# Presenter access. One block per role, one assignment per presenter.

resource "azurerm_role_assignment" "presenter_dev_owner" {
  for_each = var.presenter_object_ids

  scope                = azurerm_resource_group.dev.id
  role_definition_name = "Owner"
  principal_id         = each.value
  principal_type       = "User"
}

# Needed for the portal drift in Act 5.
resource "azurerm_role_assignment" "presenter_prod_contributor" {
  for_each = var.presenter_object_ids

  scope                = azurerm_resource_group.prod.id
  role_definition_name = "Contributor"
  principal_id         = each.value
  principal_type       = "User"
}

resource "azurerm_role_assignment" "presenter_tfstate_blob" {
  for_each = var.presenter_object_ids

  scope                = azurerm_storage_container.tfstate.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = each.value
  principal_type       = "User"
}
