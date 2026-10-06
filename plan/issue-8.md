I read `spec/issue-8.md`, SPEC.md §2, §3, §5.2, §7.4–7.10 and §12, the merged `bootstrap/` root, the README "Bootstrap (run once)" section and the earlier plan comments. Nothing blocks this ticket. #5 is merged: `bootstrap/main.tf` creates `rg-livepoll-dev` and `rg-livepoll-prod`, the state account `stlivepolltfjd01` and the `tfstate` container, and it gives the presenter Owner on the dev RG and Storage Blob Data Contributor on `tfstate`. `infra/` doesn't exist yet, and this ticket creates it.

# Plan: #8 infra: vote store on dev

## Ground rules for the builder

- **Don't edit `tasks/plan.md`, `plan/` or `spec/`.** They belong to the loop.
- **You have no Azure credentials, and this planning machine had no network** (`releases.hashicorp.com` and `registry.terraform.io` both refused connections). So any proof you can get before merge is static.
  - Try to install the latest Terraform 1.16.x into `/tmp` and call it by full path. Then run `/tmp/terraform -chdir=infra init -backend=false`, `validate` and `fmt -check -recursive`.
  - If the download or provider install fails, **say so in the PR body**. Then move `fmt`/`validate`/lock-file generation into the presenter checklist. Don't claim checks you didn't run.
  - All three acceptance criteria and the portal check are live checks. They go in the presenter checklist (Step 6). Don't tick them yourself.
- **Scope.** Only these are in scope: the backend and provider, the variables, the env files, the two data sources, the vote storage account and the `votes` table, and a short README section.
  - Out of scope, owned by #9 or later: Container Apps environment, container app, app identity, `app_table` role assignment, `outputs.tf`, and the poll question/options/colour variables.
  - **No `prevent_destroy`**, because the `act4-prevent-destroy` branch adds it.
  - **No `shared_access_key_enabled = false`**, because Act 6 does that.
- **Commits:** one per step that changes files, each ending in `(#8)`. Example: `infra: app-team provider and partial azurerm backend (#8)`.
- Never commit `*.tfstate`, `.terraform/`, `terraform.tfvars` or real GUIDs. A subscription id counts as a real GUID.

## Decisions the spec left open

1. **The shared backend settings go in `terraform.tf`, and only `key` goes in `envs/*.backend.hcl`.**
   - In `terraform.tf`: `backend "azurerm" { resource_group_name = "rg-livepoll-tfstate", storage_account_name = "stlivepolltfjd01", container_name = "tfstate", use_azuread_auth = true }`.
   - In `envs/dev.backend.hcl`: `key = "infra-dev.tfstate"`. In `envs/prod.backend.hcl`: `key = "infra-prod.tfstate"`.
   - Why: the location is the same for both envs. Writing it once means it can't drift between the two files, and `use_azuread_auth` can't be forgotten. The `.hcl` files then show exactly what differs per environment, which matches the comments on these files in §3.
   - Add a "must match bootstrap's state account" comment on the account name, as bootstrap did.
2. **No `subscription_id` variable. The provider reads `ARM_SUBSCRIPTION_ID` from the environment.**
   - azurerm ≥ 4 requires a subscription id, but `-var-file=envs/dev.tfvars` must not prompt (AC1). The repo is public, and bootstrap kept the id out of committed files.
   - The presenter runs `export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)`, which goes in the README. #11 sets the same variable from `vars.AZURE_SUBSCRIPTION_ID`.
   - Set the provider to `provider "azurerm" { features {} storage_use_azuread = true }`, with a one-line comment that Act 6 turns key auth off.
   - Versions: `required_version = "~> 1.16"` and azurerm `~> 5.8` (D16).
3. **`variable "environment"` lives in `main.tf`, not in `variables.tf`.** §5.2 says `main.tf` is the slide and must contain `variable "environment"` with its `validation` (`contains(["dev", "prod"], var.environment)`). Everything else goes in `variables.tf`, which gets a one-line comment pointing at `main.tf` for `environment`. I took the slide requirement over the ticket's "variables.tf" wording, because the spec states it outright.
4. **Variables in `variables.tf`:** only `vote_storage_account_name` (string, no default). Give it a validation: `can(regex("^[a-z0-9]{3,24}$", …))`, so a bad name fails at plan rather than at apply.
   - **No `location` variable.** Use `data.azurerm_resource_group.this.location`. Bootstrap owns the region.
   - **No resource group variable.** Use `locals { resource_group_name = "rg-livepoll-${var.environment}" }`, so tfvars hold only what actually differs.
   - The poll question/options/colour variables come with #9, which uses them. Don't declare unused variables now.
5. **Vote account names:** `stlivepolldevjd01` and `stlivepollprodjd01`. They match bootstrap's `jd01` suffix and the `stlivepoll{env}<suffix>` rule in §3, and both fit in 24 characters.
   - If you have network, check each name with `getent hosts <name>.blob.core.windows.net`. A taken name resolves.
   - Write the result, or "not checked, no network", in the PR body.
6. **`azurerm_storage_account.votes`:**
   - `account_tier = "Standard"`, `account_replication_type = "LRS"`, `min_tls_version = "TLS1_2"`, `allow_nested_items_to_be_public = false`.
   - `shared_access_key_enabled = true`, written out explicitly with the comment `# the app uses the key until Act 6`. Act 6's diff is then a one-word change.
   - `tags = { managed-by = "terraform/app-team" }` through `local.tags`.
   - Don't set `default_to_oauth_authentication`. While key auth is on, the portal browses with the key, which works for an RG Owner.
   - Name, RG and location come from the variable and the data source.
7. **`azurerm_storage_table.votes`:** `name = "votes"` as a literal, because Act 4's rename is a one-line edit to `main.tf`. Point it at the account with a reference to `azurerm_storage_account.votes`; this is the slide's cross-resource reference.
   - **Prefer `storage_account_id`**, an ARM (Azure Resource Manager) path, if the 5.8 schema has it. The presenter is only **Owner** on `rg-livepoll-dev`, which has no table *data* actions. With `storage_use_azuread = true`, a data-plane create through `storage_account_name` would return 403.
   - If 5.8 has only the data-plane argument, stop and write it in the PR as a §12 #1 finding. The presenter would then need Storage Table Data Contributor on the dev account, and that is a bootstrap change, not this ticket's.
8. **`data "azurerm_client_config" "current" {}` is declared now but not used yet.** The ticket asks for it. Give it a one-line comment saying what it exposes (the tenant, subscription and object id of whoever runs Terraform). Don't add an artificial use for it.
9. **Lock file:** commit `infra/.terraform.lock.hcl` for `darwin_arm64`, `darwin_amd64` and `linux_amd64`, as bootstrap did. If there is no network, leave it to the presenter: `terraform -chdir=infra providers lock -platform=…` after their first `init`, then commit the file. Add that line to the README section.
10. **Slide comments in `main.tf`:** one line each on the data source ("owned by bootstrap, we only read it"), the cross-resource reference and the `environment` validation. The `sensitive` output comes with #9.

## Steps

### Step 1: Provider and partial backend (S)
**Files:** `infra/terraform.tf`, and `infra/.terraform.lock.hcl` if you have network.
- Write decisions 1 and 2.
- Before writing, check the backend and provider argument names against the azurerm 5.8 docs or `providers schema -json`.

**Proof:** `/tmp/terraform -chdir=infra init -backend=false` resolves azurerm 5.8.x. `providers lock` writes the three platforms.

### Step 2: Variables and env files (S, after Step 1)
**Files:**
- `infra/main.tf`: only the `variable "environment"` block for now.
- `infra/variables.tf`
- `infra/envs/dev.backend.hcl` and `infra/envs/prod.backend.hcl`: one `key` line each.
- `infra/envs/dev.tfvars`: `environment = "dev"` and `vote_storage_account_name = "stlivepolldevjd01"`.
- `infra/envs/prod.tfvars`: the same for prod.

**Proof:**
- `validate` and `fmt -check -recursive infra` pass.
- `/tmp/terraform -chdir=infra console -var environment=staging -var vote_storage_account_name=x <<< 'var.environment'` should report the validation error. If `console` doesn't run validations, check the conditions as expressions in `console` (as #7 did): `contains(["dev","prod"],"staging")` → false, and `can(regex("^[a-z0-9]{3,24}$","stLivepoll"))` → false.

### Step 3: Data sources, vote storage account and table (M, after Step 2)
**File:** `infra/main.tf`
- Add `data.azurerm_resource_group.this` (name from the local), `data.azurerm_client_config.current`, `locals { resource_group_name, tags }`, and the resources from decisions 6–8 and 10.
- Dump `providers schema -json | jq '.provider_schemas[].resource_schemas.azurerm_storage_account, .azurerm_storage_table'`, and write the argument names you used into `tasks/notes.md`.
- Read the azurerm 5.x upgrade guide for renamed or removed storage arguments.
- **Risk to check:** if the 5.8 docs say `azurerm_storage_account` reads queue or static-website properties through the data plane, add a note to the PR. The presenter has no data roles on dev, so the first apply could 403. The mitigation is the provider's `features { storage { data_plane_available = false } }`, if 5.8 still has it, but **only** if the table resource is ARM-based. Don't set it pre-emptively.

**Proof:**
- `validate` checks against the 5.8 schema, so it catches wrong argument names. `fmt -check -recursive infra` passes.
- `grep -n 'prevent_destroy\|shared_access_key_enabled = false' infra/` returns nothing.

### Step 4: README "Dev environment (laptop)" section (S, after Step 3)
**File:** `README.md`. Add the section after "Bootstrap (run once)", with these commands:
1. `az login`
2. `export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)`
3. `terraform -chdir=infra init -backend-config=envs/dev.backend.hcl`
4. `plan -var-file=envs/dev.tfvars`, then `apply -var-file=envs/dev.tfvars`. The paths are relative to `infra/` when you use `-chdir`.
5. Add the lock-file line from decision 9 only if the lock file isn't committed.

Also add one sentence: prod is never applied from the laptop (D5).

**Proof:** Read the section and check that each path and flag matches Steps 1–2.

### Step 5: Self-review (XS, after Step 4)
Check with grep or by reading:
- None of the out-of-scope resources from the ground rules are present.
- No subscription GUID anywhere.
- The state account name matches `bootstrap/main.tf` `local.state_storage_account_name`.
- `git status` shows no `.terraform/` and no state.

Run the final static check: `init -backend=false && validate && fmt -check -recursive infra`.

### Step 6: PR with the presenter's post-merge checklist (XS)
The PR body states:
- the chosen account names and the result of the name check
- which static checks ran, or that they didn't run because there was no network
- the 5.8 argument names you used for the table (§12 #1)

Then add this checklist, unticked:
1. Run the README steps 1–4 against dev. `az storage account show -n stlivepolldevjd01 -g rg-livepoll-dev` succeeds. `az storage table list --account-name stlivepolldevjd01 --auth-mode key` lists `votes`. `az storage blob list --account-name stlivepolltfjd01 -c tfstate --auth-mode login -o table` shows `infra-dev.tfstate`. (AC1)
2. Run `plan -var-file=envs/dev.tfvars` a second time. It shows "No changes". (AC2)
3. Scratch edit in `main.tf`: `LRS` → `GRS`, then `plan`. Expect `~ account_replication_type`, update in place. Revert.
4. Scratch edit: table `votes` → `votes2`, then `plan`. Expect `-/+` (forces replacement). Revert. **Don't apply either edit.** Paste both plan lines into the PR (AC3, §12 #5). If replication shows a replacement instead, flag it on the ticket, because Act 4's story depends on it.
5. If the lock file isn't committed: `terraform -chdir=infra providers lock -platform=darwin_arm64 -platform=darwin_amd64 -platform=linux_amd64`, then commit the file.
6. Portal: `rg-livepoll-dev` shows the account with tag `managed-by = terraform/app-team`, and the account's Tables blade shows `votes`.
7. Do **not** init or apply prod. CI does that in #11 and #12.

## Ordering

Steps 1 → 2 → 3 run in that order, because `validate` needs the earlier files. Step 4 can follow any time after Step 2. Steps 5 and 6 come last. Nothing here is worth splitting across parallel workers.

## Risks

| Risk | Mitigation |
|---|---|
| The 5.8 table resource is data-plane only, so the presenter (RG Owner, no data role) gets a 403. | Decision 7: check the schema first. If confirmed, report it as a §12 #1 finding in the PR instead of working around it here. |
| The provider reads account data-plane properties during refresh and gets a 403. | The note from Step 3. The presenter retries after reading the error. The `data_plane_available` fallback applies only if the table is ARM-based. |
| `ARM_SUBSCRIPTION_ID` isn't set. | The provider fails with a clear "subscription ID" error. README step 2 covers it. |
| No network for the builder, so no `validate` or lock file before merge. | The PR says so honestly. The presenter checklist covers `fmt`, `validate` and the lock file. |
| A vote account name is taken. | Change one line in the relevant `envs/*.tfvars`. Nothing else references the name yet. |
