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

`bootstrap/` creates the state storage account, the `rg-livepoll-*` resource groups, the presenter's access and the CI identity GitHub Actions logs in with (OIDC, no secrets). It stores its own state in the container it creates, so the very first run starts with local state and then moves it. You need Terraform 1.16, the Azure CLI and Owner on the subscription.

1. `az login`
2. `cp bootstrap/terraform.tfvars.example bootstrap/terraform.tfvars` and fill in your subscription id and your own Entra object id. The file is gitignored.
3. `printf 'terraform {\n  backend "local" {}\n}\n' > bootstrap/local_override.tf` (gitignored: it swaps in a local backend for this run only).
4. `terraform -chdir=bootstrap init`, then `terraform -chdir=bootstrap apply`. If the apply fails with a 403 on the new storage account, your blob role is still propagating: wait a few minutes and apply again.
5. `rm bootstrap/local_override.tf`
6. `terraform -chdir=bootstrap init -migrate-state` and answer `yes`. If it returns 403, wait a few minutes: the blob role from step 4 is still propagating.
7. `terraform -chdir=bootstrap plan` must show "No changes".
8. `rm bootstrap/terraform.tfstate bootstrap/terraform.tfstate.backup`
9. If `bootstrap/.terraform.lock.hcl` is not committed yet: `terraform -chdir=bootstrap providers lock -platform=darwin_arm64 -platform=darwin_amd64 -platform=linux_amd64`, then commit it.

After this, on any clone, plain `terraform -chdir=bootstrap init` uses the remote state, signed in with `az login`, because account keys are turned off.
