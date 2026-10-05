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
