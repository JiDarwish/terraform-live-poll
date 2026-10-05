locals {
  # Fixed, globally unique name. The backend block can't use variables.
  state_storage_account_name = "stlivepolltfjd01" # must match bootstrap/terraform.tf

  github_owner           = "JiDarwish"
  github_repository_name = "terraform-live-poll"
  github_repository      = "${local.github_owner}/${local.github_repository_name}"
  github_oidc_issuer     = "https://token.actions.githubusercontent.com"

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

# Presenter access. One assignment per role.

resource "azurerm_role_assignment" "presenter_dev_owner" {
  scope                = azurerm_resource_group.dev.id
  role_definition_name = "Owner"
  principal_id         = var.presenter_object_id
  principal_type       = "User"
}

# Needed for the portal drift in Act 5.
resource "azurerm_role_assignment" "presenter_prod_contributor" {
  scope                = azurerm_resource_group.prod.id
  role_definition_name = "Contributor"
  principal_id         = var.presenter_object_id
  principal_type       = "User"
}

resource "azurerm_role_assignment" "presenter_tfstate_blob" {
  scope                = azurerm_storage_container.tfstate.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.presenter_object_id
  principal_type       = "User"
}

# CI identity. GitHub Actions logs in with OIDC: no app registration, no secrets.
# It lives in the tfstate RG, out of reach of its own Contributor rights on prod.

resource "azurerm_user_assigned_identity" "github" {
  name                = "id-livepoll-github"
  resource_group_name = azurerm_resource_group.tfstate.name
  location            = azurerm_resource_group.tfstate.location
  tags                = local.tags
}

# PR plans.
resource "azurerm_federated_identity_credential" "github_pull_request" {
  name                      = "fc-github-pull-request"
  user_assigned_identity_id = azurerm_user_assigned_identity.github.id
  issuer                    = local.github_oidc_issuer
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = "repo:${local.github_repository}:pull_request"
}

# Pushes to main and the drift check.
resource "azurerm_federated_identity_credential" "github_main" {
  name                      = "fc-github-main"
  user_assigned_identity_id = azurerm_user_assigned_identity.github.id
  issuer                    = local.github_oidc_issuer
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = "repo:${local.github_repository}:ref:refs/heads/main"

  # Azure returns 409 on concurrent credential writes to one identity, so write them in turn.
  depends_on = [azurerm_federated_identity_credential.github_pull_request]
}

# The prod apply job, behind the prod environment.
resource "azurerm_federated_identity_credential" "github_prod" {
  name                      = "fc-github-environment-prod"
  user_assigned_identity_id = azurerm_user_assigned_identity.github.id
  issuer                    = local.github_oidc_issuer
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = "repo:${local.github_repository}:environment:prod"

  depends_on = [azurerm_federated_identity_credential.github_main]
}

# CI access.
# Demo shortcut: one identity with write on prod, used for both plan and apply.
# Real life: plan uses a separate read-only identity (Reader, plus blob read on state),
# federated only to pull_request. Apply uses a write identity federated only to
# environment:prod, and its RBAC Administrator assignment gets a `condition` that
# limits which roles it can grant (for example only Storage Table Data Contributor).

resource "azurerm_role_assignment" "ci_prod_contributor" {
  scope                = azurerm_resource_group.prod.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.github.principal_id
  principal_type       = "ServicePrincipal"
}

# Lets CI grant the app's managed identity its data role in prod.
resource "azurerm_role_assignment" "ci_prod_rbac_admin" {
  scope                = azurerm_resource_group.prod.id
  role_definition_name = "Role Based Access Control Administrator"
  principal_id         = azurerm_user_assigned_identity.github.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "ci_tfstate_blob" {
  scope                = azurerm_storage_container.tfstate.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.github.principal_id
  principal_type       = "ServicePrincipal"
}
