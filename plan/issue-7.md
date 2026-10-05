# Plan: #7 Bootstrap: GitHub environment and Actions variables

I read `spec/issue-7.md`, SPEC.md §5.1, §6, §10 and §12, the current `bootstrap/` root (#5 and #6 are both merged), `plan/issue-6.md` and the "Bootstrap (run once)" section of `README.md`. Nothing blocks this ticket:

- #6 is merged. `bootstrap/main.tf` already has `azurerm_user_assigned_identity.github` and `local.github_repository`.
- `bootstrap/outputs.tf` already has `ci_identity_client_id`.
- The only human input still missing is Fokke's GitHub login. It goes in through a tfvars variable, so the code can be built without it.

## Ground rules for the builder

- **This machine has no `terraform` and no Azure or GitHub credentials for this repo.** As in #6, everything you can prove before merge is static:
  - Install the latest Terraform 1.16.x into `/tmp` from `releases.hashicorp.com`.
  - Run `/tmp/terraform -chdir=bootstrap init -backend=false`, then `validate`, then `fmt -check`.
  - All three acceptance criteria and the `plan → no changes` check are live checks. They go into a checklist for the presenter to run after merge (Step 5).
- **Scope:**
  - In scope: the `github` provider, the `prod` environment, the collaborator, three Actions variables, one new variable, and the README.
  - Out of scope: workflows, `reset.sh` changes, and deployment branch policies.
- **Commits:** one per step that changes files, each ending in `(#7)`. For example: `infra: github provider and prod environment with required reviewers (#7)`.
- Never commit a token, real GUIDs, `*.tfstate`, `.terraform/` or `terraform.tfvars`.

## Decisions the spec left open

1. **The token reaches the provider through the environment, never through a variable.** The README tells the presenter to run `export GITHUB_TOKEN=$(gh auth token)` before `plan`/`apply`. The `provider "github"` block has no `token` argument.
   - Why: a token in a variable or tfvars is one step from ending up in a commit or a plan file. Provider config is never written to state.
   - The default `gh` token scopes (`repo`, `read:org`) cover environments, variables and collaborators.
   - The provider may also fall back to `gh auth token` when no token is set. Check the provider docs. Even if it does, keep the explicit `export` in the README so the behaviour does not depend on the provider version.
2. **Provider version: pin `~> <major>.<minor>` of the current `integrations/github` release.**
   - Look up the latest release with `curl -s https://registry.terraform.io/v1/providers/integrations/github/versions | jq -r '.versions[].version' | sort -V | tail -1`. Do not use a version from memory.
   - Add it to `required_providers` in `bootstrap/terraform.tf` as `source = "integrations/github"`.
   - Put the `provider "github" { owner = local.github_owner }` block below the existing `azurerm` provider block.
3. **Split the repo slug into locals.** In the `locals` block in `main.tf`, add `github_owner = "JiDarwish"` and `github_repository_name = "terraform-live-poll"`. Redefine `github_repository = "${local.github_owner}/${local.github_repository_name}"`, so the #6 federated-credential subjects keep exactly the same strings.
   - Why: GitHub resources take the bare repo name, the provider takes the owner, and the OIDC subjects take the slug. One source avoids typos across the three.
4. **New file `bootstrap/github.tf`** (the spec names it). It holds every `github_*` resource and data source, so `main.tf` stays Azure-only.
5. **Reviewers are resolved through `data "github_user"`.** The environment's `reviewers.users` takes numeric user IDs, not logins.
   - `data "github_user" "presenter"` uses `username = local.github_owner`. Ji owns the repo.
   - `data "github_user" "second_reviewer"` uses `username = var.second_reviewer_github_login`.
6. **New variable `second_reviewer_github_login`** in `bootstrap/variables.tf`. The description says it is Fokke's GitHub login, without the `@`, and the second required reviewer on `prod`.
   - Add `validation` with `can(regex("^[A-Za-z0-9-]{1,39}$", ...))` and an error message that says "a GitHub login, without @". RE2 has no lookahead, so this is the closest regex.
   - The variable has no default. The presenter must supply it.
   - Add a commented line to `terraform.tfvars.example` that tells the presenter to use the exact letter case of the login. See the risks table.
   - Why a variable and not a local: the spec lists `variables.tf`, and the login is the human input that is still missing. A neutral role name keeps a person's name out of resource addresses.
7. **`github_repository_environment.prod`:**
   - `environment = "prod"` and `repository = local.github_repository_name`.
   - A `reviewers { users = [presenter id, second reviewer id] }` block.
   - `prevent_self_review = false`, set explicitly, with a one-line comment: the solo presenter (D11) must be able to approve their own push.
   - Leave `deployment_branch_policy` unset (any branch). Narrowing it is outside this spec. The approval is the gate the demo shows.
   - Leave `wait_timer` and `can_admins_bypass` unset. Before writing the resource, dump its schema (Step 1). If `reviewers.users` is a list and not a set, sort the IDs, so that `plan` does not report drift when GitHub returns them in another order.
8. **`github_repository_collaborator.second_reviewer`:**
   - `repository = local.github_repository_name`, `username = var.second_reviewer_github_login`.
   - `permission = "push"`. The API calls write access "push".
   - Do not add `depends_on` between the collaborator and the environment. On a public repo everyone has read access, which is enough to be listed as a reviewer, so the environment does not wait for the invite to be accepted.
9. **Three repo-level `github_actions_variable` resources**, not environment-scoped. PR plans (`pull_request`, no environment) need them too.
   - `AZURE_CLIENT_ID` = `azurerm_user_assigned_identity.github.client_id`.
   - `AZURE_TENANT_ID` = `azurerm_user_assigned_identity.github.tenant_id`. Use `data "azurerm_client_config"` only if Step 1's schema shows the identity has no `tenant_id` attribute.
   - `AZURE_SUBSCRIPTION_ID` = `var.subscription_id`.
   - Write them as three explicit resources, not `for_each`. This matches the style of #6, and `grep` can count them.
   - No `github_actions_secret` anywhere. Add a one-line comment: OIDC means there is no secret to store.
10. **No new outputs.** The GitHub objects are checked with `gh`.
11. **Lock file:** `bootstrap/.terraform.lock.hcl` is still uncommitted. README step 9 already makes the presenter generate it for all platforms, and it will now include `integrations/github`. Do not commit a lock file from the builder's `/tmp` run, because it would hold only `linux_amd64` hashes.

## Steps

### Step 1: Toolchain, provider version and schema check (XS, no commit)
1. Install Terraform 1.16.x into `/tmp`.
2. Find the github provider version (decision 2).
3. Temporarily add the `required_providers` entry, run `init -backend=false`, and dump the schemas of these with `providers schema -json | jq`:
   - `github_repository_environment`: the shape of the `reviewers` block, and whether `users` is a set or a list.
   - `github_repository_collaborator`: the `permission` values.
   - `github_actions_variable`: whether it uses `variable_name` and `value`.
   - `data.github_user`: whether `id` is a string or a number.
   - `azurerm_user_assigned_identity`: whether it exports `tenant_id`.
4. Write the argument names into `tasks/notes.md`.

**Proof:** `validate` is clean on the tree with only the provider added. Do not commit this alone; it goes into Step 2.

### Step 2: Provider, locals, variable, prod environment with required reviewers (S, after Step 1)
**Files:** `bootstrap/terraform.tf` (decision 2), `bootstrap/main.tf` (locals only, decision 3), `bootstrap/variables.tf` and `bootstrap/terraform.tfvars.example` (decision 6), new `bootstrap/github.tf` (decisions 5 and 7).

**Proof:**
- `fmt -check -recursive bootstrap` and `validate` are clean.
- `grep -o 'repo:[^"]*' bootstrap/main.tf` still shows the three subjects from #6, unchanged.
- `validate` with `-var second_reviewer_github_login=@fokke` (through a `-var` on `plan` is not possible offline) proves nothing. Instead, check the validation with `/tmp/terraform -chdir=bootstrap console` and `can(regex(...))` against `fokke`, `@fokke` and `a b`. Expected results: true, false, false.

This step goes first because the required-reviewer gate is the risk named in `tasks/plan.md` (§12 #6). Fail fast on it.

### Step 3: Collaborator and Actions variables (S, after Step 2)
**File:** `bootstrap/github.tf` (decisions 8 and 9).

**Proof:**
- `fmt -check` and `validate` are clean.
- `grep -c 'resource "github_actions_variable"' bootstrap/github.tf` returns 3.
- `grep -rn 'github_actions_secret\|github_actions_environment_secret' bootstrap/` returns nothing.
- `grep -n 'token' bootstrap/*.tf` shows no `token =` argument.

### Step 4: README (XS, after Step 3)
**File:** `README.md`, "Bootstrap (run once)":
- Opening sentence: add "the GitHub `prod` environment with its required reviewers and the Actions variables CI reads".
- Prerequisites: add the GitHub CLI, signed in as the repo owner.
- Step 1 becomes `az login` plus `gh auth login` and `export GITHUB_TOKEN=$(gh auth token)`, with one sentence explaining why the token is not in tfvars.
- Step 2: add "and the second reviewer's GitHub login".
- After step 7, one line: the second reviewer must accept the collaborator invite from their GitHub notifications or e-mail.
- The "on any clone" paragraph also needs `GITHUB_TOKEN` exported.

**Proof:** `git diff README.md` touches only the bootstrap section, and the step numbers stay the same.

### Step 5: Self-review and PR with the presenter's post-merge checklist (XS, last)
**Self-review:**
- The only `github_*` resources are 1 environment, 1 collaborator and 3 variables, plus 2 `data "github_user"`.
- There are no secrets and no `token` argument.
- The OIDC subjects are byte-identical to #6.
- No lock file, tfvars file or state file is staged.

**Final static proof:** `fmt -check -recursive bootstrap`, then `init -backend=false && validate`.

The PR body carries this checklist, unticked. Do not tick any acceptance-criteria box yourself.
1. Run `export GITHUB_TOKEN=$(gh auth token)` and set `second_reviewer_github_login` in `terraform.tfvars`, with the exact letter case.
2. `terraform -chdir=bootstrap init -upgrade`, then `plan`. The plan should add only 1 environment, 1 collaborator and 3 Actions variables. Azure should show no changes.
3. Run `apply`, then `plan`. The second plan should say "No changes". This is the Verification item.
4. `gh api repos/JiDarwish/terraform-live-poll/environments/prod --jq '.protection_rules[] | select(.type=="required_reviewers") | .reviewers[].reviewer.login'` should list both logins (AC 1). If the API refuses required reviewers on GitHub Free, stop. That answers §12 #6 as "no", and the fallback in `tasks/plan.md` is GitHub Pro.
5. `gh variable list -R JiDarwish/terraform-live-poll` should show the three variables, and `gh secret list -R JiDarwish/terraform-live-poll` should be empty (AC 2).
6. Fokke accepts the invite. Then `gh api repos/JiDarwish/terraform-live-poll/collaborators/<login>/permission --jq .permission` should return `write`.
7. Check that Fokke can approve a deployment, using a throwaway workflow that is never merged:
   - On a scratch branch, push `.github/workflows/env-check.yml` with `on: push` and one job that has `environment: prod` and runs `run: echo ok`.
   - Fokke approves the waiting run in the Actions UI, and the run goes green (AC 3).
   - Delete the branch, then remove the run with `gh run delete`.
8. Run `terraform plan` again after the invite is accepted. It should still say "No changes". A pending invite turning into a collaborator must not cause drift.

## Ordering

Steps run in order: 1 → 2 → 3 → 4 → 5. Step 3 uses the locals from Step 2, and Step 4 describes the finished root. The ticket is too small to split across parallel workers.

## Risks

| Risk | Mitigation |
|---|---|
| Required reviewers are refused on a public repo on GitHub Free (§12 #6) | Step 2 builds this first. Checklist item 4 is the real test. Fallback: GitHub Pro (`tasks/plan.md`) |
| The collaborator resource compares logins case-sensitively, so `plan` shows constant drift | The tfvars example and checklist item 1 say to use the exact case. Checklist item 8 re-runs `plan` after the invite is accepted |
| The order of `reviewers.users` causes drift | Step 1 checks whether it is a set. If it is a list, sort the IDs (decision 7) |
| `reset.sh` (a later ticket) applies bootstrap unattended and now needs `GITHUB_TOKEN` | Out of scope here. Say so in the PR body so the `reset.sh` ticket exports it |
| The `environment:prod` OIDC subject can be used from any branch, because there is no deployment branch policy | A required approval still gates it. Narrowing it to `main` is a later decision. Mention it in the PR as a talking point |
