**Milestone:** M2 · Bootstrap · **Size:** S · **Spec:** [SPEC.md](https://github.com/JiDarwish/terraform-live-poll/blob/main/SPEC.md) §5.1, §12 #6

Blocked by #6

## What
Use the `integrations/github` provider in `bootstrap/` (token from `gh auth token`) to create the `prod` environment with Ji and Fokke as required reviewers, and the Actions variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`. No repo secrets. Add Fokke as a collaborator with write access. Confirms §12 #6: required reviewers work on a public repo on GitHub Free.

## Acceptance criteria
- [ ] `gh api repos/JiDarwish/terraform-live-poll/environments/prod` lists both required reviewers
- [ ] `gh variable list` shows the three variables; `gh secret list` is empty
- [ ] Fokke has write access and can approve a `prod` deployment

## Verification
- [ ] `terraform -chdir=bootstrap plan` → no changes

## Files likely touched
- `bootstrap/terraform.tf`
- `bootstrap/github.tf`
- `bootstrap/variables.tf`

## Needs a human
Fokke's GitHub username; Fokke accepts the collaborator invite.

---
_Starts in `triage`. Swap `triage` for `ready` to approve it for an agent._
