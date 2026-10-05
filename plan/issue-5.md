I've read the spec (§5.1, §10, §12, D13 and D16), the repo layout, `.gitignore` and the earlier plan comments. Nothing blocks this ticket: `bootstrap/` doesn't exist yet and doesn't depend on any unmerged work. This machine has no `terraform` or `az`, so the plan below gives the builder a static proof (fmt, validate, lock file). The Azure-side checks go to Ji as a checklist that runs after merge.

# Plan: #5 Bootstrap: state storage, resource groups and presenter access

**Before you start:**
- **Do not edit `tasks/plan.md` or anything in `plan/` or `spec/`.** They belong to the loop, not to this ticket.
- `bootstrap/` does not exist yet. This ticket creates it. It holds **only** the resources this ticket names. The CI identity (#6) and the GitHub environment and variables (#7) come later. Do not add the `integrations/github` provider or `id-livepoll-github` here.
- **The planning machine has no `terraform` and no `az`, and the builder has no Azure credentials.** Before merge, the proof is static: `fmt`, `init -backend=false`, `validate` and a committed lock file. Every Azure-side acceptance criterion is a step Ji runs after merge (Step 7). Install Terraform 1.16.x into `/tmp` from `releases.hashicorp.com` (the latest 1.16 patch) and call it by full path.
- **Fokke's object id is not needed to build this.** It goes into Ji's local, gitignored `bootstrap/terraform.tfvars` at apply time. Do not commit real object ids.
- **Commits:** one commit per step that changes files, each with the `(#5)` suffix, for example `infra: bootstrap state storage account and tfstate container (#5)` or `docs: bootstrap first run in README (#5)`.

## Decisions the spec left open

1. **The backend is fully written out in `bootstrap/terraform.tf`, with no partial config.** The first acceptance criterion says plain `terraform -chdir=bootstrap init` must reach remote state, so it cannot rely on `-backend-config` flags. Use `backend "azurerm" { resource_group_name = "rg-livepoll-tfstate", storage_account_name = "<literal>", container_name = "tfstate", key = "bootstrap.tfstate", use_azuread_auth = true }`. `infra/` and `data-platform/` keep the partial config §5.2 describes. This root does not.
2. **For the first run, a local override file stands in for the backend. Nobody edits the committed backend.** Ji creates `bootstrap/local_override.tf` containing `terraform { backend "local" {} }`. In an override file, Terraform replaces the backend block with this one. Ji runs `init` and `apply`, deletes the override, then runs `init -migrate-state`. This is safer than commenting the backend block in and out, because the committed file never changes. Add `override.tf` and `*_override.tf` to the root `.gitignore` (next to the Terraform block) so nobody can commit the override.
3. **The state storage account name is a fixed literal, `stlivepolltf<suffix>`. There is no `random_string`.** The backend block can't use variables, and §5.2 already prefers fixed names. Put the name in `locals { state_storage_account_name = "..." }` in `main.tf`, and keep the same literal in the backend block. Add a one-line comment at each place: "must match bootstrap/terraform.tf" and "must match local.state_storage_account_name".
   - Choose a short suffix, such as `jd01`, that keeps the name at 24 characters or fewer, using lowercase letters and digits only.
   - Check that the name is free: `getent hosts stlivepolltf<suffix>.blob.core.windows.net` must return nothing, because a taken name resolves.
   - Write the chosen name in the PR description.
4. **The state account settings.** All of these go on `azurerm_storage_account.tfstate`:
   - `account_tier = "Standard"` and `account_replication_type = "LRS"`. State is small, and versioning covers mistakes.
   - `min_tls_version = "TLS1_2"` and `shared_access_key_enabled = false`.
   - `allow_nested_items_to_be_public = false`.
   - `default_to_oauth_authentication = true`, so the portal browses the container with Entra. Without it, the portal tries the account key first, and the Act 3 portal walk-through shows an error.
   - A `blob_properties` block with `versioning_enabled = true`, `delete_retention_policy { days = 7 }` and `container_delete_retention_policy { days = 7 }`. The spec gives no number for container soft delete, so I chose 7 to match the blob setting.
5. **`prevent_destroy = true` on the state storage account and on the `tfstate` container.** `reset.sh` runs `bootstrap apply -auto-approve` unattended. A bad diff that wants to replace the account would delete every state file. This makes that apply fail instead. It costs two lines and is a talking point.
6. **`azurerm_storage_container.tfstate` uses `storage_account_id`, not `storage_account_name`.** That way the container is created through Azure Resource Manager, which works with key auth off, and its `id` is the ARM path (`…/blobServices/default/containers/tfstate`). The `Storage Blob Data Contributor` assignment needs that path as its scope. Set `container_access_type = "private"`.
7. **`var.presenter_object_ids` is `map(string)`, keyed by first name: `{ ji = "…", fokke = "…" }`.** The spec gives only the name, and a list is the other option. A map gives readable state addresses (`azurerm_role_assignment.presenter_dev_owner["fokke"]`), and its keys stay stable if someone is added or removed. Add a `validation` block that requires every value to look like a GUID, so a pasted UPN fails at plan time rather than at apply.
8. **Three explicit role-assignment resources**, each with `for_each = var.presenter_object_ids`:
   - `presenter_dev_owner`: role `Owner`, scope `rg-livepoll-dev`.
   - `presenter_prod_contributor`: role `Contributor`, scope `rg-livepoll-prod`.
   - `presenter_tfstate_blob`: role `Storage Blob Data Contributor`, scope the container.

   Use one `for_each` per role, not `setproduct`. The code is shown to the room, and three plain blocks read better than a computed map. Set `principal_type = "User"` on each, which avoids the "principal not found" error from replication delay.
9. **Provider:** `provider "azurerm" { features {}, subscription_id = var.subscription_id, storage_use_azuread = true }`.
   - azurerm 4 and later require `subscription_id`. It is a variable because it is the same subscription for everyone, but it does not belong in a public repo.
   - `storage_use_azuread` is needed because key auth is off on the state account.
   - Versions: `required_version = "~> 1.16"` and `azurerm` `source = "hashicorp/azurerm"`, `version = "~> 5.8"` (D16).
10. **Other variables:** `location` defaults to `"westeurope"` (the team is in Amsterdam, and the spec names no region). Every resource gets `tags = { managed-by = "terraform/bootstrap" }`, which matches the `managed-by` convention that §5.2 and §7 use for the ownership story.
11. **Commit `bootstrap/.terraform.lock.hcl`** with hashes for `darwin_arm64` (presenter Macs), `linux_amd64` (CI and this machine) and `darwin_amd64`. Generate them with `terraform providers lock -platform=…`. The `.gitignore` comment already says the lock file is committed.
12. **Outputs** for #6, #8 and `reset.sh` to use: `state_resource_group_name`, `state_storage_account_name`, `state_container_name`, `state_container_id` (the scope for #6's CI role), `dev_resource_group_name` and `prod_resource_group_name`. Do not output the account keys or a connection string.
13. **Add a short "Bootstrap (run once, Ji)" section to `README.md`** with the first-run procedure. That procedure is the one documented human workflow, and `reset.sh` assumes it has run. `RUNBOOK.md` is out of scope.

## Steps

### Step 1: Provider, backend and lock file (S)
**Files:** `bootstrap/terraform.tf`, `bootstrap/.terraform.lock.hcl`, `.gitignore`
- In `terraform.tf`, add a `terraform {}` block with `required_version`, `required_providers` and the full backend (decision 1), plus the `provider "azurerm"` block (decision 9).
- Put a 3–4 line comment above the backend that explains the first run and points to the README section.
- Add `override.tf` and `*_override.tf` to `.gitignore`.
- Before writing the arguments, check the azurerm 5.8 docs on registry.terraform.io for the backend and provider argument names (§12 says check against 5.8, not memory).

**Proof:**
- `/tmp/terraform -chdir=bootstrap init -backend=false` downloads azurerm 5.8.x.
- `terraform providers lock -platform=darwin_arm64 -platform=darwin_amd64 -platform=linux_amd64` writes the lock file.
- `git check-ignore bootstrap/local_override.tf` matches.

### Step 2: Variables and example tfvars (S, after Step 1)
**Files:** `bootstrap/variables.tf`, `bootstrap/terraform.tfvars.example`
- `variables.tf` declares `subscription_id` (string, no default), `location` (default `"westeurope"`) and `presenter_object_ids` (`map(string)` with the GUID validation from decision 7). Each variable has a one-line `description`.
- `terraform.tfvars.example` uses placeholder GUIDs, with comments on how to find each value:
  - your own object id: `az ad signed-in-user show --query id -o tsv`
  - someone else's: `az ad user show --id <upn> --query id -o tsv`
  - the subscription: `az account show --query id -o tsv`
- Add one comment line saying the file is copied to the gitignored `terraform.tfvars`, and that **anyone who runs `reset.sh` needs the same presenter map**. A missing entry would remove that person's access.

**Proof:**
- `cp terraform.tfvars.example /tmp/t.tfvars`, then `terraform -chdir=bootstrap validate` passes.
- `terraform -chdir=bootstrap console -var-file=/tmp/t.tfvars <<< 'var.presenter_object_ids'` prints the map.
- Swap in a non-GUID value such as `fokke@xomnia.com` and check that the validation error appears. Use `plan -refresh=false -var-file=…` if `console` does not trigger validation. That plan call fails at auth after validation, which is enough.

### Step 3: Resource groups, state account and container (M, after Step 2)
**File:** `bootstrap/main.tf`
- `locals { state_storage_account_name = "stlivepolltf<suffix>" }` (decision 3, with its "must match" comment).
- Three resource groups: `azurerm_resource_group.tfstate`, `azurerm_resource_group.dev` and `azurerm_resource_group.prod`, named exactly as in §3.
- `azurerm_storage_account.tfstate` with decisions 4 and 5. Comment each security setting in one line, because this file is shown in Act 3.
- `azurerm_storage_container.tfstate` with decisions 5 and 6.
- Use a `local.tags` map for `managed-by`.
- Check every argument name against the azurerm 5.8 docs. Watch especially `blob_properties.*`, `shared_access_key_enabled`, `default_to_oauth_authentication` and the container's `storage_account_id`. Check the 5.x upgrade guide for anything renamed or removed.

**Proof:**
- `terraform -chdir=bootstrap fmt -check` and `validate` are clean. `validate` checks against the downloaded 5.8 schema, so it catches wrong argument names.
- `grep -n` shows `shared_access_key_enabled = false`, `TLS1_2`, `versioning_enabled = true` and both `days = 7`.

### Step 4: Presenter role assignments (S, after Step 3)
**File:** `bootstrap/main.tf`
- Add the three `azurerm_role_assignment` resources from decision 8.
  - Scopes: `azurerm_resource_group.dev.id`, `azurerm_resource_group.prod.id` and `azurerm_storage_container.tfstate.id`.
  - Use `role_definition_name`, `principal_id = each.value` and `principal_type = "User"`.
- One comment on the prod Contributor block: "needed for the portal drift in Act 5".
- Check that the container's `id` attribute in 5.8 is the ARM ID. If the docs list a separate `resource_manager_id`, use that for the scope.

**Proof:** `fmt -check` and `validate` are clean. `grep -c 'resource "azurerm_role_assignment"' bootstrap/main.tf` returns 3.

### Step 5: Outputs (XS, after Step 4)
**File:** `bootstrap/outputs.tf`. Add the outputs from decision 12, each with a `description`.

**Proof:** `fmt -check` and `validate` are clean.

### Step 6: README first-run section (S, after Steps 1–5)
**File:** `README.md`

Add a new section named "Bootstrap (run once, Ji)" after "Run locally". It contains these numbered commands:
1. `az login`
2. `cp bootstrap/terraform.tfvars.example bootstrap/terraform.tfvars` and fill it in.
3. `printf 'terraform {\n  backend "local" {}\n}\n' > bootstrap/local_override.tf`
4. `terraform -chdir=bootstrap init`, then `apply`.
5. `rm bootstrap/local_override.tf`
6. `terraform -chdir=bootstrap init -migrate-state` and answer `yes`. If it returns 403, wait a few minutes: the blob role from step 4 is still propagating.
7. `terraform -chdir=bootstrap plan` must show "No changes".
8. `rm bootstrap/terraform.tfstate bootstrap/terraform.tfstate.backup`

After the numbered steps, add one line saying that after this, anyone in `presenter_object_ids` runs plain `terraform -chdir=bootstrap init`.

**Proof:** Read the section and check that each command matches the file names and backend from Steps 1–3.

### Step 7: Self-review, then the PR with Ji's post-merge checklist (XS, after Step 6)
Self-review with grep or by reading:
- No `github` provider and no CI identity (#6 and #7 own those).
- No real GUIDs anywhere.
- The storage account name is the same in `terraform.tf` and `main.tf`.
- The lock file covers three platforms.
- No `*.tfstate` and no `.terraform/` are staged.

Final static proof: `fmt -check -recursive bootstrap` and `init -backend=false && validate`, both clean.

**The PR body** names the chosen storage account name and has this checklist, unticked, for Ji. Do not tick the acceptance-criteria boxes yourself.
1. Run the README bootstrap steps 1–8. Fokke's object id is the human input.
2. In a fresh clone, run `terraform -chdir=bootstrap init`. It configures the azurerm backend, no `terraform.tfstate` exists afterwards, and `plan` returns "No changes".
3. Ji and Fokke each run `az storage blob list --account-name <name> -c tfstate --auth-mode login`. It lists `bootstrap.tfstate`.
4. `az storage blob list --account-name <name> -c tfstate --auth-mode key` is refused. Expect `KeyBasedAuthenticationNotPermitted`, or a "no key available" error.
5. `az role assignment list --assignee <oid> --all -o table` for each presenter shows Owner on `rg-livepoll-dev`, Contributor on `rg-livepoll-prod` and Storage Blob Data Contributor on the `tfstate` container.
6. In the portal, check that the state account shows blob versioning on, blob soft delete 7 days and container soft delete on.

## Ordering

Steps 1 → 2 → 3 → 4 → 5 run in that order, because `validate` needs every earlier file. Step 6 can be written any time after Step 3, but it is easier to check after Step 5. Step 7 is last. Nothing here is worth splitting across parallel workers.

## Risks

| Risk | Mitigation |
|---|---|
| Argument names changed in azurerm 5.x. The spec flags 5.x as new. | `validate` against the downloaded 5.8 schema (Steps 3–4), plus a read of the 5.x upgrade guide. |
| The first apply fails on a data-plane read of the new account, because Ji's blob role was created in the same apply and is not yet active. | Wait 2–5 min and run `apply` again. The PR checklist says this. |
| `init -migrate-state` returns 403 right after the first apply, for the same propagation reason. | The README step 6 note: wait and retry. The local state is safe until step 8. |
| The chosen storage account name gets taken before Ji applies. | Change the literal in the two marked places. Nothing else depends on it until #6 and #8. |
| Fokke runs `reset.sh` with a `terraform.tfvars` whose presenter map differs from Ji's, so the apply removes someone's access. | The `.example` comment (Step 2) says so. #7 or the `reset.sh` ticket can decide to commit the ids. They are not secret, but committing them is out of scope here. |
| The provider still issues key-based calls with keys disabled. | `storage_use_azuread = true` is set from the start (decision 9). If the first apply still hits a key error, record it in the PR for §12 #4. |
