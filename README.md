# terraform-live-poll

A live room poll, deployed and changed only through Terraform, used to teach Terraform to new data engineers.

Work in progress:
- [SPEC.md](SPEC.md) — what we are building and why
- [tasks/plan.md](tasks/plan.md) — the build order; each task is a [GitHub issue](https://github.com/JiDarwish/terraform-live-poll/issues)

## Run locally

You need Docker. From the repo root:

```sh
cd app && docker compose up
```

This starts the app, [Azurite](https://learn.microsoft.com/azure/storage/common/storage-use-azurite) (Azure's local storage emulator) and a one-shot `table-init` step that creates the `votes` table. Then open `http://<your-laptop-LAN-IP>:8000/` on a phone on the same network. If the phone cannot connect, allow incoming connections on port 8000 in your laptop's firewall.

- `http://<your-laptop-LAN-IP>:8000/results` is the projector page: the question, live bars, the total and a QR code to the vote page. The QR code uses whatever host the browser used, so open it via the LAN IP, not `localhost`, or phones cannot reach it.
- `http://localhost:8000/api/results` shows the counts as JSON.
- `POLL_QUESTION="Other?" docker compose up -d app` starts a new poll at zero. Older votes stay in the table.
- Votes survive `docker compose down`. Use `docker compose down -v` to delete them.
- `docker compose stop azurite` shows what happens when the vote store is down. `/` and `/results` still load, with the banner "Can't reach the vote store", and `docker compose logs app` shows `vote store unreachable: <cause>`. `docker compose start azurite` recovers.
- Local runs use `AUTH_MODE=key` (a connection string). `AUTH_MODE=identity` also needs `STORAGE_ACCOUNT_NAME` and `AZURE_CLIENT_ID` (the user-assigned managed identity). It only works on Azure, because Azurite has no managed identity.

Run the tests:

```sh
pip install -r app/requirements-dev.txt
pytest app/tests
```

To also run the test against a real Azurite, set `AZURITE_CONNECTION_STRING` (with `TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;`) while `docker compose up` is running.

## Bootstrap (run once)

`bootstrap/` creates the state storage account, the `rg-livepoll-*` resource groups, the presenter's access, the CI identity GitHub Actions logs in with (OIDC, no secrets), the GitHub `prod` environment with its required reviewers and the Actions variables CI reads. It stores its own state in the container it creates, so the very first run starts with local state and then moves it. You need Terraform 1.16, the Azure CLI, Owner on the subscription and the GitHub CLI, signed in as the repo owner.

1. `az login`, `gh auth login`, then `export GITHUB_TOKEN=$(gh auth token)`. The GitHub provider reads the token from the environment, so it never lands in tfvars or a plan file.
2. `cp bootstrap/terraform.tfvars.example bootstrap/terraform.tfvars` and fill in your subscription id, your own Entra object id and the second reviewer's GitHub login. The file is gitignored.
3. `printf 'terraform {\n  backend "local" {}\n}\n' > bootstrap/local_override.tf` (gitignored: it swaps in a local backend for this run only).
4. `terraform -chdir=bootstrap init`, then `terraform -chdir=bootstrap apply`. If the apply fails with a 403 on the new storage account, your blob role is still propagating: wait a few minutes and apply again.
5. `rm bootstrap/local_override.tf`
6. `terraform -chdir=bootstrap init -migrate-state` and answer `yes`. If it returns 403, wait a few minutes: the blob role from step 4 is still propagating.
7. `terraform -chdir=bootstrap plan` must show "No changes".
   The second reviewer must now accept the collaborator invite, from their GitHub notifications or e-mail.
8. `rm bootstrap/terraform.tfstate bootstrap/terraform.tfstate.backup`
9. If `bootstrap/.terraform.lock.hcl` is not committed yet: `terraform -chdir=bootstrap providers lock -platform=darwin_arm64 -platform=darwin_amd64 -platform=linux_amd64`, then commit it.

After this, on any clone, plain `terraform -chdir=bootstrap init` uses the remote state, signed in with `az login`, because account keys are turned off. `plan` and `apply` also need `GITHUB_TOKEN` exported, as in step 1.

## Dev environment (laptop)

`infra/` is the app team's root module. It runs against dev from the laptop and against prod only from CI: never init or apply prod from the laptop. Each environment has its own state file (`infra-dev.tfstate`, `infra-prod.tfstate`) in the bootstrap state container. Run bootstrap first.

1. `az login`
2. `export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)`. The provider reads the subscription from the environment, so it never lands in a committed file.
3. `terraform -chdir=infra init -backend-config=envs/dev.backend.hcl`
4. `terraform -chdir=infra plan -var-file=envs/dev.tfvars`, then `terraform -chdir=infra apply -var-file=envs/dev.tfvars`. With `-chdir`, the `envs/` paths are relative to `infra/`.
5. If `infra/.terraform.lock.hcl` is not committed yet: `terraform -chdir=infra providers lock -platform=darwin_arm64 -platform=darwin_amd64 -platform=linux_amd64`, then commit it.

Known gap: the first apply creates the storage account, then fails with a 403 on the `votes` table. azurerm 5.8 creates tables through the Table data plane, and with `storage_use_azuread = true` it signs in with your Entra login. Owner on `rg-livepoll-dev` grants no data access. You need `Storage Table Data Contributor` on `rg-livepoll-dev`, and bootstrap does not grant it yet.
