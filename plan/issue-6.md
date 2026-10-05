# Plan: #6 Bootstrap: CI identity with OIDC federation

I read `spec/issue-6.md`, SPEC.md §5.1 and §6, the current `bootstrap/` root (from #5, merged), `README.md` "Bootstrap (run once)" and `plan/issue-5.md`. Nothing blocks this ticket. Every resource it needs to reference already exists in `bootstrap/main.tf`: `azurerm_resource_group.prod`, `azurerm_resource_group.tfstate` and `azurerm_storage_container.tfstate`. No new provider is needed, so the lock file does not change.

## Ground rules for the builder

- **Neither this machine nor the builder has `terraform`, `az` or Azure credentials.** As in #5, the proof before merge is static. Install the latest Terraform 1.16.x into `/tmp` from `releases.hashicorp.com` and call it by full path. Then run `/tmp/terraform -chdir=bootstrap init -backend=false`, `validate` and `fmt -check`. The two Azure-side acceptance criteria and the `plan → no changes` check go into a checklist for the presenter, who runs it after merge (Step 5).
- **Scope:** only the CI identity, its three federated credentials, its three role assignments and the outputs. Do not add the `integrations/github` provider, the `prod` environment or the Actions variables. Those belong to #7.
- **Commits:** one per step that changes files, each with the `(#6)` suffix. For example: `infra: bootstrap CI identity with OIDC federated credentials (#6)`.
- Do not commit real GUIDs, and do not stage `*.tfstate` or `.terraform/`.

## Decisions the spec left open

1. **The identity lives in `rg-livepoll-tfstate`, not in `rg-livepoll-prod`.** The CI identity has Contributor on prod. If the identity sat in prod, CI could delete or change its own identity. The presenter could do the same during the Act 5 portal drift, because they are Contributor on prod. In the tfstate RG, CI has only blob data rights on one container, so the identity is out of reach of the principal it represents. The tfstate RG is also bootstrap-only and has the same lifecycle as the identity.
2. **The repository slug goes in a local, not a variable:** `local.github_repository = "JiDarwish/terraform-live-poll"`. It is fixed for this repo, and #7's `integrations/github` provider can reuse it. Add `github_oidc_issuer = "https://token.actions.githubusercontent.com"` to the same `locals` block in `main.tf`. The audience is `["api://AzureADTokenExchange"]`, which is Azure's default for GitHub OIDC.
3. **Three explicit `azurerm_federated_identity_credential` resources, not `for_each`, chained with `depends_on`.** Azure rejects concurrent federated-credential writes on one user-assigned identity with a 409 (`ConcurrentFederatedIdentityCredentialsWritesForSingleManagedIdentity`). `reset.sh` applies bootstrap unattended, so a flaky first apply is not acceptable. Chaining makes Terraform write the three credentials one after another. A one-line comment says why. Explicit resources also make "exactly three" visible on screen and easy to check with `grep`.
   - Resource and credential names:
     - `github_pull_request` → `fc-github-pull-request`, subject `repo:${local.github_repository}:pull_request`
     - `github_main` → `fc-github-main`, subject `…:ref:refs/heads/main`
     - `github_prod` → `fc-github-environment-prod`, subject `…:environment:prod`
   - These three subjects cover every job in §6. PR plans use `pull_request`. Apply job 1 runs on a push to main, and `drift.yml` runs on schedule or dispatch on main; both use `ref:refs/heads/main`. Apply job 2 runs with `environment: prod` and uses `environment:prod`.
4. **Argument names come from the 5.8 schema, not from memory.** In the 4.x line, `parent_id` was deprecated in favour of `user_assigned_identity_id`, and `resource_group_name` changed status. Before you write the resource, run `/tmp/terraform -chdir=bootstrap providers schema -json | jq '.provider_schemas[].resource_schemas.azurerm_federated_identity_credential'` after `init -backend=false`. Use the non-deprecated argument that points at the identity. Omit `resource_group_name` if the schema no longer requires it.
5. **Role assignments follow the existing presenter pattern:** one resource per role, with `principal_type = "ServicePrincipal"` and `principal_id = azurerm_user_assigned_identity.github.principal_id`. Use these names:
   - `ci_prod_contributor` (`Contributor` on `azurerm_resource_group.prod.id`)
   - `ci_prod_rbac_admin` (`Role Based Access Control Administrator` on the same scope; use that exact name)
   - `ci_tfstate_blob` (`Storage Blob Data Contributor` on `azurerm_storage_container.tfstate.id`)

   CI gets no access to `rg-livepoll-dev`. D5 says only the laptop changes dev.
6. **The §5.1 talking point is a comment block directly above the three CI role assignments.** It states the demo shortcut: one identity with write on prod, used for both plan and apply. It also states the real-life version: a separate read-only identity for plan (Reader plus blob read on state, federated only to `pull_request`), and a write identity federated only to `environment:prod`, whose RBAC Administrator assignment gets a `condition` limiting which roles it can grant (for example only Storage Table Data Contributor). Keep it to 4–6 lines, in the voice of a slide callout. The resources do not change because of it.
7. **Outputs:** `ci_identity_client_id` (`azurerm_user_assigned_identity.github.client_id`) and `ci_identity_principal_id`, each with a `description`. The client id is what `AZURE_CLIENT_ID` will hold, and the presenter needs it for a manual `az login --federated-token` debug. The principal id is what `az role assignment list --assignee` takes. No tenant output: #7 can read `tenant_id` from the identity or from `azurerm_client_config` inside the same root.
8. **Update the README in one place.** In "Bootstrap (run once)", the opening sentence lists what `bootstrap/` creates. Add "the CI identity GitHub Actions logs in with (OIDC, no secrets)". Leave the steps alone. They already apply this root as a whole, and `plan` → "No changes" in step 7 now covers the identity too.

## Steps

### Step 1: Toolchain and schema check (XS, no commit)
Install Terraform 1.16.x into `/tmp`. Run `/tmp/terraform -chdir=bootstrap init -backend=false` and confirm it picks up azurerm 5.8.x. Dump the schemas for `azurerm_user_assigned_identity` and `azurerm_federated_identity_credential` (decision 4), and write the argument names into `tasks/notes.md`.
**Proof:** `validate` is clean on the untouched tree, which is the baseline.

### Step 2: Identity and federated credentials (S, after Step 1)
**File:** `bootstrap/main.tf`
- Add `github_repository` and `github_oidc_issuer` to the existing `locals` block.
- Under a new `# CI identity. GitHub Actions logs in with OIDC: no app registration, no secrets.` heading, after the presenter block, add `azurerm_user_assigned_identity.github`: name `id-livepoll-github`, in `azurerm_resource_group.tfstate` (name and location), `tags = local.tags`.
- Add the three federated credentials from decision 3 with `issuer = local.github_oidc_issuer` and `audience = ["api://AzureADTokenExchange"]`. Then chain them: `github_main` `depends_on` `github_pull_request`, and `github_prod` `depends_on` `github_main`, with a one-line 409 comment.

**Proof:**
- `fmt -check` and `validate` are clean.
- `grep -c 'resource "azurerm_federated_identity_credential"' bootstrap/main.tf` returns 3.
- `grep -o 'repo:[^"]*' bootstrap/main.tf` shows exactly the three subjects, with the `${local.github_repository}` interpolation.

### Step 3: CI role assignments with the talking-point comment (S, after Step 2)
**File:** `bootstrap/main.tf`. Add the comment from decision 6, then the three role assignments from decision 5.
**Proof:**
- `fmt -check` and `validate` are clean.
- `grep -c 'resource "azurerm_role_assignment"' bootstrap/main.tf` returns 6 (3 presenter + 3 CI).
- `grep -n 'Role Based Access Control Administrator'` matches once.
- Read through the file: no CI assignment targets `azurerm_resource_group.dev`.

### Step 4: Outputs and README (XS, after Step 2)
**Files:** `bootstrap/outputs.tf` (decision 7), `README.md` (decision 8).
**Proof:** `fmt -check` and `validate` are clean. The README sentence names the CI identity, and the numbered steps are unchanged (`git diff README.md` is one line).

### Step 5: Self-review and PR with the presenter's post-merge checklist (XS, last)
Self-review:
- No `github` provider, environment or variables in the tree.
- No real GUIDs.
- The identity is in the tfstate RG.
- The three subjects match the spec character for character.
- The lock file is unchanged.

Final static proof: `fmt -check -recursive bootstrap` and `init -backend=false && validate`, both clean.

The PR body carries this checklist, unticked. Do not tick the acceptance-criteria boxes yourself.
1. `terraform -chdir=bootstrap plan` shows 1 identity, 3 federated credentials and 3 role assignments to add, and nothing else.
2. Run `apply`. If one credential write still returns a 409, run `apply` again and note it in the PR, because that means decision 3 did not hold.
3. `terraform -chdir=bootstrap plan` → "No changes".
4. `az identity federated-credential list -g rg-livepoll-tfstate --identity-name id-livepoll-github -o table` shows exactly three rows, with the subjects from the spec.
5. `az role assignment list --assignee $(terraform -chdir=bootstrap output -raw ci_identity_principal_id) --all -o table` shows Contributor and Role Based Access Control Administrator on `rg-livepoll-prod`, Storage Blob Data Contributor on `…/containers/tfstate`, and nothing else.

## Ordering

The steps run in order: 1 → 2 → 3, and then 4. Step 3 needs the identity from Step 2. Step 4 can go any time after Step 2. Step 5 is last. This ticket is too small to split across parallel workers.

## Risks

| Risk | Mitigation |
|---|---|
| azurerm 5.8 renamed or removed arguments on `azurerm_federated_identity_credential` | Step 1 reads the schema, and `validate` runs against the downloaded schema |
| The 409 on concurrent credential writes still happens despite `depends_on` | The checklist tells the presenter to apply again and record it. The chain also makes deletes run one at a time |
| Role assignments take up to 30 min to propagate | Nothing in this ticket uses them. #11 is the first OIDC login, and it comes later |
| For #11, not this ticket: with RG-scoped rights only, `infra/`'s azurerm provider may get a 403 when it tries to register resource providers across the subscription | Flagged here so #11 sets `resource_provider_registrations` correctly. Do not widen CI's rights in this ticket |
