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

- `http://localhost:8000/api/results` shows the counts as JSON.
- `POLL_QUESTION="Other?" docker compose up -d app` starts a new poll at zero. Older votes stay in the table.
- Votes survive `docker compose down`. Use `docker compose down -v` to delete them.

Run the tests:

```sh
pip install -r app/requirements-dev.txt
pytest app/tests
```

To also run the test against a real Azurite, set `AZURITE_CONNECTION_STRING` (with `TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;`) while `docker compose up` is running.
