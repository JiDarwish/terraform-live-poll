# GitHub side of CI: the prod approval gate and the Actions variables the workflows read.

data "github_user" "presenter" {
  username = local.github_owner
}

data "github_user" "second_reviewer" {
  username = var.second_reviewer_github_login
}

resource "github_repository_environment" "prod" {
  repository  = local.github_repository_name
  environment = "prod"

  prevent_self_review = false # the solo presenter must be able to approve their own push

  reviewers {
    users = [
      data.github_user.presenter.id,
      data.github_user.second_reviewer.id,
    ]
  }
}

# Fokke reviews prod deployments. Write access; the API calls it "push".
# Takes effect once they accept the invite.
resource "github_repository_collaborator" "second_reviewer" {
  repository = local.github_repository_name
  username   = var.second_reviewer_github_login
  permission = "push"
}

# Repo-level, so PR plans (no environment) read them too.
# No github_actions_secret: CI logs in with OIDC, so there is no secret to store.

resource "github_actions_variable" "azure_client_id" {
  repository    = local.github_repository_name
  variable_name = "AZURE_CLIENT_ID"
  value         = azurerm_user_assigned_identity.github.client_id
}

resource "github_actions_variable" "azure_tenant_id" {
  repository    = local.github_repository_name
  variable_name = "AZURE_TENANT_ID"
  value         = azurerm_user_assigned_identity.github.tenant_id
}

resource "github_actions_variable" "azure_subscription_id" {
  repository    = local.github_repository_name
  variable_name = "AZURE_SUBSCRIPTION_ID"
  value         = var.subscription_id
}
