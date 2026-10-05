**Milestone:** M2 · Bootstrap · **Size:** M · **Spec:** [SPEC.md](https://github.com/JiDarwish/terraform-live-poll/blob/main/SPEC.md) §5.1

Blocked by nothing

## What
`bootstrap/` creates `rg-livepoll-tfstate`, the state storage account and `tfstate` container (blob versioning, 7-day blob soft delete, container soft delete, `shared_access_key_enabled = false`, TLS 1.2), `rg-livepoll-dev`, `rg-livepoll-prod`, and the presenter role assignments from `var.presenter_object_id`. The first apply uses local state, then `terraform init -migrate-state` moves it to `bootstrap.tfstate` in the container it just made.

## Acceptance criteria
- [ ] On a clean clone, `terraform -chdir=bootstrap init` uses the remote state (no local `.tfstate`)
- [ ] The presenter can `az storage blob list --auth-mode login` on `tfstate`; access with an account key is refused
- [ ] The presenter has Owner on `rg-livepoll-dev`, Contributor on `rg-livepoll-prod`, Storage Blob Data Contributor on `tfstate`

## Verification
- [ ] `terraform -chdir=bootstrap plan` → no changes
- [ ] Portal: versioning and soft delete are on

## Files likely touched
- `bootstrap/terraform.tf`
- `bootstrap/main.tf`
- `bootstrap/variables.tf`
- `bootstrap/outputs.tf`
- `bootstrap/terraform.tfvars.example`

## Needs a human
The presenter's Entra object id is needed for `presenter_object_id`.

---
_Starts in `triage`. Swap `triage` for `ready` to approve it for an agent._
