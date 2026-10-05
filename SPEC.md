# v2 spec: Live Poll, a Terraform demo you can vote on

**Status:** draft for review, 2026-10-02
**Author:** the presenter (grilled by Claude)
**Scope:** this spec stands alone. It replaces an earlier demo, and nothing from that demo is needed to build this one.
**Presenter:** one person, **alone**. The presenter is also the only admin: they run bootstrap, own the subscription and approve prod. Nobody else is in the room to help, so every step must work for one person.

---

## 1. The idea in one paragraph

We deploy a **live room poll**. A QR code is on the projector. Trainees scan it and vote from their phones, and the projector shows the results live. Terraform controls everything about the poll: the question, the options, the colour, and where the votes are stored. So **every Terraform change is visible on 20 phones**. The demo then puts this small app through what real engineering teams deal with every week: a colleague changes prod in the portal, a change that quietly deletes data, a secret in the state file, two people applying at the same time, and part of the system moving to another team. Every change to prod goes through GitHub Actions.

**The thesis of the day:** *everything goes through plan.* Terraform tells you what it is about to do before it does it, and keeps a written record (state) of what it did. Everything else follows from those two facts.

**The rule the room sees all day without being told:** *The presenter's laptop changes dev. Only CI changes what is on your phone.*

---

## 2. Decisions already made

| # | Decision |
|---|---|
| D1 | The app is a live room poll that we write ourselves. No open-source app fits: the Azure voting app images were deleted from MCR, `example-voting-app` hardcodes its hosts and passwords, and Claper's questions are set up in its UI rather than by Terraform. |
| D2 | This demo carries the whole training day. Every hands-on moment of the 4 hours runs on the poll. |
| D3 | CI/CD runs **live** in the session, on a **public** personal repo `JiDarwish/terraform-live-poll`. |
| D4 | The presenter's existing work subscription (tenant Xomnia B.V., the presenter is Owner). |
| D5 | Two environments, **dev** and **prod**. Same code. Separate state files. Separate `tfvars`. dev is changed only from the laptop. prod is changed only by CI, after an approval. |
| D6 | **The room votes on prod all day.** One QR code, which never changes. |
| D7 | A **data platform team** takes over the vote store mid-session, with its own root folder and its own state file in the same repo. The handover includes the "two owners fighting" beat. |
| D8 | Drift comes in three kinds: a visible change on prod, CI catching it, and drift we accept on purpose (`ignore_changes`). |
| D9 | The secret story ends with **managed identity + `shared_access_key_enabled = false`**. The key **stays in state**, because the resource always exports it, but Azure now refuses it. We never claim it disappears. |
| D10 | Locking is shown with two terminals. `apply` holds the lock while it waits at the prompt. |
| D11 | The presenter plays every role: two terminals with different colours and titles (`APP TEAM`, `DATA TEAM`). Every "other person" step also has a fallback script. |
| D12 | The app team finds the vote store after the handover with a **`data` source**. `terraform_remote_state` is named as the trap: it needs read access to the other team's whole state, secrets included. |
| D13 | No local state anywhere, except the first run of `bootstrap/` (which is then migrated, see §5.1). |
| D14 | Reset between sessions = **one tag + one script**. |
| D15 | App stack: Python 3.12, FastAPI, `azure-data-tables`, `azure-identity`. |
| D16 | azurerm provider `~> 5.8`. Terraform `~> 1.16`, the same version on laptops and in CI. |
| D17 | Container Apps environment: **one per environment**. Rehearsal rule in §11. |

---

## 3. Repository layout

```
terraform-live-poll/                 # public, github.com/JiDarwish/terraform-live-poll
├── README.md                        # what this is, how to run it, link to RUNBOOK.md
├── RUNBOOK.md                       # the presenter's choreography, act by act (written in implementation)
├── CODEOWNERS                       # /data-platform/ owned by "data team" (illustrative)
├── app/                             # the poll app (§4)
│   ├── main.py
│   ├── templates/                   # vote.html, results.html
│   ├── static/                      # one CSS file, one small JS file
│   ├── tests/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── compose.yaml                 # app + Azurite, for running locally
├── bootstrap/                       # run once by the presenter. State, identities, RGs, GitHub env (§5.1)
├── infra/                           # APP TEAM root module, used for dev and prod (§5.2)
│   ├── terraform.tf                 # required_providers, partial azurerm backend
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── envs/
│       ├── dev.backend.hcl          # key = "infra-dev.tfstate"
│       ├── dev.tfvars
│       ├── prod.backend.hcl         # key = "infra-prod.tfstate"
│       └── prod.tfvars
├── data-platform/                   # DATA TEAM root module. Exists from day one, manages nothing (§5.3)
│   ├── terraform.tf
│   ├── main.tf                      # empty at session-start, with a comment
│   ├── variables.tf
│   └── envs/                        # same four files, keys data-platform-{dev,prod}.tfstate
├── scenarios/                       # one fallback script per "other person" step (§8)
├── scripts/
│   └── reset.sh                     # §10
└── .github/workflows/               # §6
```

**Naming** (`{env}` = `dev` | `prod`):

| Thing | Name |
|---|---|
| Resource groups | `rg-livepoll-tfstate`, `rg-livepoll-dev`, `rg-livepoll-prod` |
| State storage account | `stlivepolltf<suffix>` |
| Vote storage account | `stlivepoll{env}<suffix>`. **Fixed name in `tfvars`**, no `random_string` (§5.2 explains why) |
| Vote table | `votes` |
| Container Apps environment | `cae-livepoll-{env}` |
| Container App | `ca-livepoll-{env}` |
| App identity | `id-livepoll-app-{env}` |
| CI identity | `id-livepoll-github` |

---

## 4. The app

### 4.1 What a trainee sees

- **`/` (phone):** the question in big type, one large button per option, the env badge (`DEV` orange / `PROD` green), and the poll colour as the accent. Tap a button → "Thanks, look at the screen" + a link to results. A cookie stops a phone voting twice in the same poll (a soft guard, not real security).
- **`/results` (projector):** the question, horizontal bars with counts, the total votes, a **QR code** pointing to `/`, and a small footer: `env · auth mode (key | managed identity) · revision`. Refreshes every 2 s.

The **auth mode in the footer** matters: it is how the room sees Act 6 happen.

### 4.2 Configuration (env vars, all set by Terraform)

| Var | Example | Notes |
|---|---|---|
| `POLL_QUESTION` | `How confident are you with Terraform?` | |
| `POLL_OPTIONS` | `What's Terraform?\|Heard of it\|Used it\|I could teach this` | pipe-separated |
| `POLL_COLOR` | `#2f7d5b` | accent colour |
| `ENVIRONMENT` | `prod` | drives the badge |
| `AUTH_MODE` | `key` or `identity` | |
| `STORAGE_CONNECTION_STRING` | (secret ref) | only when `AUTH_MODE=key` |
| `STORAGE_ACCOUNT_NAME` | `stlivepollprodxx01` | only when `AUTH_MODE=identity` |
| `AZURE_CLIENT_ID` | (UAMI client id) | only when `AUTH_MODE=identity` |
| `TABLE_NAME` | `votes` | comes from `azurerm_storage_table.votes.name` |

### 4.3 Behaviour

- **`poll_id` = first 8 hex characters of `sha256(question + options)`.** A new question starts at zero votes. Older votes stay in the table under their own `poll_id`. This is why drift on the question is so visible: the counts reset on every phone.
- **Storage:** one entity per vote. `PartitionKey = poll_id`, `RowKey = uuid4`, property `option`. Results = query the partition and count in Python. That is fine for 50 people.
- **The app never creates the table.** Terraform owns it, which is what makes the "rename the table" beat work.
- **Auth:** `key` → `TableServiceClient.from_connection_string`. `identity` → `ManagedIdentityCredential(client_id=AZURE_CLIENT_ID)` with endpoint `https://{account}.table.core.windows.net`.
- **If the vote store can't be reached:** the page still renders and shows a banner, "Can't reach the vote store". The server logs the cause. Reads retry with backoff, which covers slow role-assignment propagation.
- **Endpoints:** `GET /`, `POST /api/vote`, `GET /api/results` (JSON), `GET /results`, `GET /healthz`.
- **QR code:** drawn on the server as inline SVG (`segno`). Its URL comes from the request host, so the app never needs to know its own FQDN. That avoids a Terraform dependency cycle.
- **No CDN, no build step, no JS framework.** One CSS file and about 30 lines of JS for the refresh.
- **Size target:** `main.py` under about 200 lines. A trainee should understand it in one minute.

### 4.4 Image

- `python:3.12-slim`, runs as a non-root user, `uvicorn` on port 8000.
- Built for **`linux/amd64`** (the presenter uses an Apple Silicon Mac).
- Pushed to `ghcr.io/jidarwish/terraform-live-poll:<git-sha>` by the `app-image` workflow.
- **The GHCR package must be made public once, by hand.** New GHCR packages are private by default.
- Terraform pins the tag through `var.app_image_tag`. **The one image must support both auth modes**, so no app release happens during the session.

### 4.5 Local run and tests

- `docker compose up` runs the app against **Azurite** (Azure's local storage emulator) in key mode.
- `pytest`: `poll_id` is stable, counting works, `AUTH_MODE` picks the right client, the page renders when storage is down.

---

## 5. Infrastructure

### 5.1 `bootstrap/` — run once by the presenter

The first run uses local state. **Then its state moves into the state container it just created** (`terraform init -migrate-state`, key `bootstrap.tfstate`), so `reset.sh` and any fresh clone use the remote state, not the first laptop's local file. One sentence for the room: *someone always has to go first.*

Creates:

| Resource | Details |
|---|---|
| `rg-livepoll-tfstate` | |
| State storage account + container `tfstate` | blob versioning on, blob soft delete 7 days, container soft delete, `shared_access_key_enabled = false`, TLS 1.2 |
| `rg-livepoll-dev`, `rg-livepoll-prod` | **Owned by bootstrap.** `infra/` reads them with a `data` source. That is the first, small "someone else owns this" example. |
| `id-livepoll-github` (user-assigned managed identity) | federated credentials for `repo:JiDarwish/terraform-live-poll:pull_request`, `…:ref:refs/heads/main`, `…:environment:prod` |
| Role: CI identity | `Contributor` + `Role Based Access Control Administrator` on `rg-livepoll-prod`. `Storage Blob Data Contributor` on the `tfstate` container. |
| Role: presenter (`var.presenter_object_id`) | `Owner` on `rg-livepoll-dev`. `Contributor` on `rg-livepoll-prod` (needed for the portal drift in Act 5, and itself a talking point). `Storage Blob Data Contributor` on `tfstate`. |
| GitHub (`integrations/github` provider) | environment `prod` with the presenter as required reviewer. Actions variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`. **No secrets**: OIDC means there are none to store. |

Why a user-assigned identity plus federated credentials instead of an Entra app registration: it needs no tenant-admin rights, and many tenants block app registrations.

Talking point for CI rights: *one identity with write on prod is the demo shortcut. In real life, plan uses a read-only identity, and the RBAC Administrator role gets a condition that limits which roles it can grant.*

### 5.2 `infra/` — the app team

**Resources at session-start:**

```
data.azurerm_resource_group.this          # owned by bootstrap
data.azurerm_client_config.current
azurerm_container_app_environment.this    # no Log Analytics: logs are streamed only (optional in azurerm)
azurerm_storage_account.votes             # Standard / LRS, tags.managed-by = "terraform/app-team"
azurerm_storage_table.votes               # "votes"
azurerm_user_assigned_identity.app
azurerm_role_assignment.app_table         # Storage Table Data Contributor → the vote storage account
azurerm_container_app.poll                # AUTH_MODE=key, secret = primary_connection_string
```

**Rules:**

- **The app identity and its role assignment exist from day one, even while the app uses the key.** Role assignments can take up to 30 min to propagate, so Act 6 must never create one live.
- **User-assigned, not system-assigned, identity:** the role assignment then does not depend on the app existing, and survives the app being replaced.
- `storage_use_azuread = true` in the provider block from day one. Otherwise Terraform loses data-plane access when key auth is turned off in Act 6. *(Verify in 5.x, §12.)*
- **Fixed storage account names in `tfvars`, no `random_string`.** That keeps the handover, `import` IDs and `reset.sh` simple. The cost: with a random suffix, losing state would make Terraform silently build a second stack under new names. With fixed names, losing state makes the plan want to create everything, and the apply would fail because the resources already exist and must be imported. That is still a true lesson, and it sets up `import` later in the day.
- `template.min_replicas = 0` in both environments. The cold start is a few seconds on the first scan, which is fine.
- `revision_mode = "Single"`.
- The poll question, options and colour live in `envs/{env}.tfvars`. Everything else is code, shared by both environments.
- **Backend:** partial config, `backend "azurerm" {}` + `-backend-config=envs/{env}.backend.hcl`, `use_azuread_auth = true`. The presenter runs `init` once, against dev only.

**Outputs:** `poll_url`, `results_url`, `storage_account_name`, `container_app_name`, and `vote_store_connection_string` with `sensitive = true` (removed again in Act 6).

**`infra/main.tf` doubles as the annotated `main.tf` slide.** It must contain a data source, a cross-resource reference, a `sensitive` output, and `variable "environment"` with a `validation` block (`dev` or `prod`). Comment each of these in one line, the way a slide callout would.

### 5.3 `data-platform/` — the data team

- **At session-start:** backend, provider and variables are present, and `main.tf` holds only a comment. `plan` says "No changes". *"This team exists. It just doesn't own anything yet."*
- **After the handover (Act 7):** `import` blocks + resource blocks for the vote storage account and table, `prevent_destroy`, `tags.managed-by = "terraform/data-platform"`, and an output `storage_account_name`.
- **`import` IDs are built from variables** (`subscription_id`, resource group, account name), so the same code imports into dev and prod. *(Check the table's import ID format in 5.x, §12.)*

---

## 6. CI/CD (GitHub Actions)

All Azure logins use **OIDC** (`azure/login` with `client-id`, `tenant-id`, `subscription-id` from repo variables). `hashicorp/setup-terraform` is pinned to the same version as the laptops.

| Workflow | Trigger | Does |
|---|---|---|
| `app-image.yml` | push to `main` touching `app/**` | test → build amd64 → push to GHCR with the SHA tag |
| `_terraform-plan.yml` | reusable (`workflow_call`) | inputs: `working_directory`, `env`. Runs `fmt -check` → `init` → `validate` → `plan -out=tfplan`, and posts or updates **one PR comment** with the plan |
| `infra-pr.yml` / `data-platform-pr.yml` | PR touching that folder | calls `_terraform-plan.yml` for **prod** |
| `_terraform-apply.yml` | reusable | job 1: plan + upload `tfplan` as an artifact. Job 2: `environment: prod` (**waits for approval**), downloads the **exact** plan file, `apply tfplan` |
| `infra-apply.yml` / `data-platform-apply.yml` | push to `main` touching that folder, plus `workflow_dispatch` | calls `_terraform-apply.yml` |
| `drift.yml` | `schedule` (daily 06:00) + `workflow_dispatch` | matrix over `infra`, `data-platform`. Runs `plan -detailed-exitcode`. Exit code 2 → job fails red **and opens or updates a GitHub issue** "Drift detected in prod" with the plan |

**The PR comment format** is what the room reads, so it gets attention:

- First line: `Plan: X to add, Y to change, Z to destroy`.
- If `Z > 0` or the output contains `forces replacement`: a bold warning line at the top, `⚠️ This plan DESTROYS resources`.
- The full plan sits in a collapsed `<details>` block, cut to fit GitHub's comment limit.

**Also in the YAML, to point at on screen:**

- `concurrency: tf-prod-${{ inputs.working_directory }}`, `cancel-in-progress: false`. This is CI's own lock, on top of the state lock.
- `permissions:` kept to the minimum per job: `id-token: write`, `contents: read`, `pull-requests: write`, `issues: write`.
- **Apply uses the plan file that was approved.** If state changed in between, Terraform refuses with "Saved plan is stale". This is narrated, not demoed.
- PRs from forks get no OIDC token, which is why the repo can be public.

**Mentioned on a slide, not built:** policy as code, a read-only plan identity, HCP Terraform.

---

## 7. The session

### 7.1 Starting state, walking into the room

- bootstrap applied and its state migrated.
- **prod deployed by CI the day before**, in key mode. The QR code works.
- **dev empty.** The presenter's terminal is `init`ed against the dev backend.
- `main` == tag `session-start`. The scenario branches (§7.3) exist.
- Two terminal profiles: **APP TEAM** (`infra/`, one colour) and **DATA TEAM** (`data-platform/`, another colour). Browser tabs: prod `/results`, dev `/results`, the GitHub repo, the portal.

### 7.2 Run sheet

Format: 4 hours, presenter-led, in a meeting room. Trainees have phones but no laptops. Audience: fresh-graduate data engineers with no Terraform experience.

| Time | Block | Where | What happens |
|---|---|---|---|
| 0:00 | Intro (10m) | slides | Who we are, the shape of the day, the thesis |
| 0:10 | **Teaser** (5m) | prod | QR up, the room votes. Explain nothing. *"By 4pm you'll know how this got here."* |
| 0:15 | Foundations (30m) | slides | What IaC is and why it exists, where Terraform fits, Terraform / OpenTofu / Bicep |
| 0:45 | Mechanics (25m) | slides | Providers, resources, data sources, state, the core workflow, reading plan symbols (`+`, `~`, `-`, `-/+`) |
| 1:10 | *break* (10m) | | |
| 1:20 | **1. Build dev** (20m) | dev, laptop | §7.4 |
| 1:40 | **2. Where state lives** (20m) | dev | §7.5. The local vs remote state slides are woven in. |
| 2:00 | **3. Through the front door** (20m) | prod, CI | §7.6. The CI/CD slide is woven in. |
| 2:20 | *break* (10m) | | |
| 2:30 | **4. Not all changes are equal** (15m) | prod, CI | §7.7 |
| 2:45 | **5. Someone touched prod** (15m) | prod | §7.8 |
| 3:00 | **6. Kill the secret** (10m) | prod, CI | §7.9 |
| 3:10 | **7. Another team takes over** (25m) | dev live → prod via PR | §7.10. The "Terraform only manages what is in state" slides come first. |
| 3:35 | Slides (10m) | slides | Modules (one slide), HCP Terraform, the pitfalls they just watched |
| 3:45 | Agentic angle (10m) | slides | Agents writing and applying Terraform. Plan output is the guardrail. |
| 3:55 | Wrap (5m) | slides | Next step: the HashiCorp Terraform Associate (004) certification |

**Cut order if running late** (cut first at the top):

1. The agentic block shrinks to 5 min
2. `-generate-config-out` in Act 7
3. `ignore_changes` in Act 5
4. The two-owners fight in Act 7 (narrate it instead)
5. "Lose the state" in Act 2

**Never cut:** the drift on prod, the forced-replacement PR, the secret in state and the managed identity switch, the handover, locking.

### 7.3 Prepared scenario branches (stacked)

One person cannot write code live and talk at the same time. Every PR except the Act 3 question is **a prepared branch**, opened with `gh pr create --head <branch>`.

| Branch | Based on | Change | Fate |
|---|---|---|---|
| `act4-replication` | `session-start` | `account_replication_type` LRS → GRS | PR, read `~`, **close** |
| `act4-rename-table` | `session-start` | table `votes` → `pollvotes` | PR, read `-/+`, **close** |
| `act4-prevent-destroy` | `session-start` | `prevent_destroy` on the account + table | **merge** |
| `act5-ignore-changes` | `act4-prevent-destroy` | `ignore_changes = [template[0].min_replicas]` | **merge** |
| `act6-managed-identity` | `act5-ignore-changes` | `AUTH_MODE=identity`, drop the secret and the sensitive output, `shared_access_key_enabled = false` | **merge** |
| `act7-handover` | `act6-managed-identity` | data-platform import + resources. infra `removed` + `data` source. | **merge** |

Because the branches are stacked, cutting Act 5 changes nothing: merging `act6` brings `act5`'s commit with it. Act 3's PR only touches `envs/prod.tfvars`, so it never conflicts with the chain.

### 7.4 Act 1 — Build dev (laptop)

1. `terraform init -backend-config=envs/dev.backend.hcl` → point at `.terraform.lock.hcl`.
2. `fmt`, `validate`, `plan -var-file=envs/dev.tfvars` → **read it out loud**, count the `+`. Ask the room what will happen.
3. `apply` → fill the wait (§11) with the portal and the dev `/results` page.
4. Open dev `/results` on the projector. *"Same app as your phones, different environment. Orange badge."*
5. `terraform output` → `vote_store_connection_string = <sensitive>`. Then `terraform state pull | jq '…primary_access_key'` → **the key, in plain text**. *"Sensitive hides it from the screen, not from the file. Hold that thought until 3pm."*

Closing beat: *"The .tf file is what I want. The state file is what Terraform did. Plan is the difference."*

### 7.5 Act 2 — Where state lives (dev)

1. **The portal:** `tfstate` container → `infra-dev.tfstate`, `infra-prod.tfstate`. *"Same JSON you would get in a local `terraform.tfstate` file. Now it lives somewhere a team can share, it's versioned, and only some people can read it."* Point at versioning, soft delete, and key auth being off.
2. **Locking:**
   - APP TEAM terminal: `apply -var-file=envs/dev.tfvars` with a small change. **Leave it at `Enter a value:`.**
   - Second terminal: `plan -var-file=envs/dev.tfvars` → **`Error acquiring the state lock`**, with Who, Operation, Created.
   - Portal: the blob shows **Lease state: Leased**.
   - Run `plan -lock-timeout=120s` in the second terminal. Type `yes` in the first. The second plan continues.
   - Name `terraform force-unlock` as the dangerous escape hatch.
   - Note: with the default `-lock-timeout=0s` the second command **fails at once**. It does not wait. Say this correctly.
3. **Lose the state:**
   - Delete `infra-dev.tfstate` in the portal.
   - `plan` → everything is `+ create`. *"Nothing changed in Azure. Everything changed in Terraform's head."* If someone applied this, it would fail on "resource already exists, import it". Point at the word *import*: it comes back in Act 7.
   - Portal → show deleted blobs → **Undelete** (or promote the previous version).
   - `plan` → no changes. *"This is why the state container has versioning."*

### 7.6 Act 3 — Through the front door (prod, CI)

1. **The room picks the next question** (and options). The presenter edits `envs/prod.tfvars` on a new branch, pushes, opens a PR.
2. While CI runs, walk through `_terraform-plan.yml`: OIDC, no secrets, `fmt`/`validate`/`plan`.
3. The PR comment: `0 to add, 1 to change, 0 to destroy`. Read the env var diff.
4. Merge → `infra-apply` → **approval** in the `prod` environment → apply → **phones change**.

*"Nobody touched prod. The pipeline did, after a human read the plan."*

### 7.7 Act 4 — Not all changes are equal (prod, CI)

1. Open the `act4-replication` and `act4-rename-table` PRs together. Both diffs are one line.
2. Replication PR: `~ update in-place`.
3. Rename PR: `⚠️ This plan DESTROYS resources`, `-/+ azurerm_storage_table.votes (forces replacement)`. *"CI just told us this PR deletes your N votes."* **Close both PRs.**
4. Open and merge `act4-prevent-destroy`. Optional: re-run the rename on top of it and Terraform refuses to plan.

*"For anything holding data, this one line turns an accident into an error message."*

### 7.8 Act 5 — Someone touched prod

1. Portal, prod Container App:
   - Change `POLL_QUESTION` to *"Is Terraform overrated?"* → new revision → **the phones show it, counts at zero**.
   - Also set min replicas to 1 (*"the on-call engineer, during an incident"*).
2. *"Why can I even do this? Because I have Contributor on prod. Real fix: nobody but CI has write on prod."*
3. Run `drift.yml` (`workflow_dispatch`) → **red**, and an issue opens with both diffs.
4. *"The question was wrong. The replicas were right."* Merge `act5-ignore-changes` → apply → **the question reverts**, the replicas stay. The phones show the room's question again, with its old votes back (same `poll_id`).

### 7.9 Act 6 — Kill the secret (prod, CI)

1. Recall Act 1's plain-text key. *"`sensitive = true` hides it from the screen, not from the state file."*
2. Merge `act6-managed-identity` → approve → apply. The **`/results` footer flips `key` → `managed identity`**, and votes keep coming in.
3. `terraform state pull` (dev, after a local apply of the same branch), or the plan comment: **the key is still in state**.
4. Try it: `az storage entity query --account-key <that key> …` → **refused**, key-based auth not permitted.

*"You can't always keep a secret out of state. You can make it worthless, and you lock the state down anyway."* One sentence on OpenTofu: it encrypts state on the client (since 1.7), and Terraform has nothing like it built in.

### 7.10 Act 7 — Another team takes over (dev live, then prod)

Setup line: *"From today the data platform team owns the vote store. The app team keeps the app."*

1. **DATA TEAM terminal (dev):** check out `act7-handover`, but run the data side first. `import` blocks + resource blocks with `managed-by = "terraform/data-platform"`.
   - `plan` → "will be imported", nothing created.
   - `apply`.
   - Optional: `plan -generate-config-out=generated.tf` to show the draft config it would generate.
2. **The fight.** APP TEAM terminal, still on the old code: `plan` → `~ tags.managed-by: "terraform/data-platform" → "terraform/app-team"`. Apply it. DATA TEAM `plan` → wants it back. *"Two owners. Each apply undoes the other. Usually it's not a tag. It's a firewall rule at 2am."* The portal tag shows whoever applied last.
3. **The fix.** APP TEAM: the branch's infra side, `removed { lifecycle { destroy = false } }` + `data "azurerm_storage_account"` + `data "azurerm_storage_table"`.
   - `plan` → "will no longer be managed by Terraform", nothing destroyed.
   - The role assignment and the container app now reference the data sources.
4. **The trap, said out loud:** *"We could read their outputs with `terraform_remote_state`. That needs read access to their whole state, and you saw at 3pm what is in a state file."* A `data` source needs only the name.
5. **Bonus truth:** the app team's state still contains `primary_access_key`, now **through the data source**. Data sources write their results into state too. It's worthless thanks to Act 6.
6. **prod:** open and merge the `act7-handover` PR → both apply workflows run → approve both → **the votes survive**, and the phones never notice.

Closing beat of the day: *"Terraform doesn't manage your cloud. It manages what is in its state. Ownership is a line in a state file, and you move it with a plan, not by hand."* Name `terraform state rm` as the old way: immediate, no plan, no review.

---

## 8. Solo-presenter support

- **`scenarios/`:** one script per "other person" step, used only if the portal is slow or something breaks:
  - `colleague-edits-prod.sh` (`az containerapp update`)
  - `oncall-scales-prod.sh`
  - `delete-dev-state.sh`
  - `restore-dev-state.sh`
  - `try-old-key.sh`
- **`RUNBOOK.md`:** the presenter's script for the day. It starts with a setup and morning-of checklist. Then, for each act:
  - a header line: act name, minutes, where it sits in the run sheet
  - a step table (example below)
  - the closing beat, quoted
  - an **"If it breaks"** table: Symptom · Cause · Live response

  Rule at the top of the runbook: *one failed command is a teaching moment, two in a row is a recording.*

  ```markdown
  ## Act 2 — Where state lives · 20 min · 1:40

  | # | Where | Do | Room sees | Say |
  |---|---|---|---|---|
  | 1 | APP TEAM | `terraform apply -var-file=envs/dev.tfvars` → stop at `Enter a value:` | plan on screen | "I'm holding the lock now." |
  | 2 | DATA TEAM | `terraform plan -var-file=envs/dev.tfvars` | `Error acquiring the state lock`, with my name | "Terraform refuses. It tells you who has it." |
  ```

  Keep it short: commands and beats, no long prose.
- **Fallback recordings** of every act, made during the final rehearsal.
- **A volunteer (optional):** a trainee types `yes` in the locking demo when the presenter says so.

---

## 9. Deck alignment (for the presenter; not an implementation task)

The presenter owns and updates the slides. These are the places where slides and demo must agree:

- **The annotated `main.tf` slide** uses `infra/main.tf`, which therefore needs: a data source, a cross-resource reference, a `sensitive` output, and a variable with a `validation` block (on `environment`).
- **The remote-state slide:** partial backend config, `use_azuread_auth`, versioning, and the lock error text from Act 2. The second command fails at once; it does not wait.
- **The CI/CD slide** becomes "you watched this": plan on PR, approval, apply the saved plan, drift on a schedule.
- **The pitfalls slide:** forced replacement of the votes table, the secret in state, two owners.

---

## 10. Reset: `scripts/reset.sh`

Run **the day before** every session. It takes about 15 min. The presenter runs it.

```
1. az group delete -n rg-livepoll-dev  --yes   (in parallel with prod)
   az group delete -n rg-livepoll-prod --yes
2. Delete every state blob in tfstate except bootstrap.tfstate
3. terraform -chdir=bootstrap apply -auto-approve   # recreates both RGs and their role assignments
4. git push --force origin session-start:main
5. gh workflow run infra-apply.yml --ref main       # then approve in the browser
6. curl -fsS <prod poll_url>/healthz                # and scan the QR with your own phone
7. gh pr list --state open → close leftovers;  gh issue list → close drift issues
```

Why it deletes the resource groups instead of running `terraform destroy`: `prevent_destroy` and the handover make destroy order-dependent. Deleting the RGs works no matter which act the last session reached.

---

## 11. Rehearsal decisions (made during the first full run, not before)

| Question | Rule |
|---|---|
| Time to create the Container Apps environment in Act 1 | Microsoft does not document it. **If it takes over 4 min:** move the environment to bootstrap as a shared "platform" environment for dev and prod, and say out loud that sharing one between dev and prod isn't good practice. |
| CI time, PR → phones | Measure. If it takes over 6 min, start Act 3's PR before the theory slide that comes before it. |
| Role propagation for the app identity | Created the day before by `reset.sh`. Confirm that Act 6 works the first time. |
| Restoring the deleted state blob | Confirm whether the portal shows Undelete or Promote version for a deleted blob with versioning plus soft delete, and write the exact clicks in the runbook. |

---

## 12. To check against current docs during implementation

The research is from 2026-10-02. **azurerm 5.x is new.** Check every argument against the 5.8 docs, not against memory or older examples.

1. Argument names in `azurerm_storage_table`, `azurerm_container_app` and `azurerm_container_app_environment` in 5.x (`storage_account_id` vs `storage_account_name`, secret and identity blocks).
2. The import ID format of `azurerm_storage_table` in 5.x.
3. With `shared_access_key_enabled = false`: does the provider still read `primary_access_key` into state? Act 6's "the key is still in state" depends on it. **If not**, Act 6 instead says "the key is gone because Azure no longer hands it out", and the Act 7 bonus truth changes the same way.
4. Is `storage_use_azuread = true` needed for Terraform to manage the table after key auth is off?
5. Does `LRS → GRS` still update in place, and does renaming a table still force replacement?
6. Do required reviewers work on GitHub Environments for a public repo on GitHub Free?
7. Is a storage account name free for reuse right after its resource group is deleted (needed by `reset.sh`)?
8. `import` block `id` built from variables (allowed since 1.6) works for both environments.

---

## 13. Out of scope

- Modules (they stay a theory slide)
- Policy as code, HCP Terraform, Terragrunt
- Separate CI identities per team
- A separate repo for the data team (one sentence in the room instead)
- Real per-user vote integrity
- Log Analytics

---

## 14. Build order and definition of done

| # | Milestone | Done when |
|---|---|---|
| M1 | App | `docker compose up` → vote on a phone over the LAN, results update within 2 s. Tests pass. Key mode works against Azurite. Identity mode is covered by a unit test here and proven against Azure in M3. |
| M2 | bootstrap | applied, state migrated, GitHub env and variables exist, the presenter can `init` dev |
| M3 | `infra/` on dev | apply from the laptop → working dev URL. `state pull` shows the key. |
| M4 | Workflows + prod | a PR shows a plan comment. Merge → approval → prod URL works. Drift workflow goes red on a portal edit and opens an issue. |
| M5 | Scenario branches | every branch in §7.3 gives the plan its act expects, checked on prod |
| M6 | Handover | Act 7 on dev and prod: the votes survive, and nothing is destroyed in any plan |
| M7 | `reset.sh` | it runs from the presenter's laptop and gets back to §7.1 |
| M8 | `RUNBOOK.md` + `scenarios/` | the presenter can run the whole session alone from the runbook |
| M9 | Full rehearsal | all acts timed, §11 decided, fallback recordings captured |

**Definition of done for v2:** the presenter runs one full rehearsal alone, from `reset.sh` to Act 7, without help.
