**Milestone:** M3 · infra on dev · **Size:** M · **Spec:** [SPEC.md](https://github.com/JiDarwish/terraform-live-poll/blob/main/SPEC.md) §5.2, §12 #1, #5

Blocked by #5

## What
The app team's root module, first slice: `terraform.tf` (azurerm `~> 5.8`, Terraform `~> 1.16`, partial `azurerm` backend with `use_azuread_auth`, `storage_use_azuread = true`), variables including `environment` with a `validation` block, `envs/{dev,prod}.{backend.hcl,tfvars}`, data sources for the RG and client config, the vote storage account (fixed name from tfvars, `managed-by = terraform/app-team`) and table `votes`. Check every argument against the azurerm 5.8 docs.

## Acceptance criteria
- [ ] `init -backend-config=envs/dev.backend.hcl` + `apply -var-file=envs/dev.tfvars` creates the account and table in `rg-livepoll-dev`; state lands at `infra-dev.tfstate`
- [ ] A second `plan` shows no changes
- [ ] Scratch edits confirm §12 #5: LRS→GRS plans `~`, renaming the table plans `-/+` (result written in the PR)

## Verification
- [ ] `terraform fmt -check && terraform validate`
- [ ] Portal: account and table exist

## Files likely touched
- `infra/terraform.tf`
- `infra/variables.tf`
- `infra/main.tf`
- `infra/envs/dev.backend.hcl`
- `infra/envs/dev.tfvars`
- `infra/envs/prod.backend.hcl`
- `infra/envs/prod.tfvars`

---
_Starts in `triage`. Swap `triage` for `ready` to approve it for an agent._
