**Milestone:** M1 · App · **Size:** M · **Spec:** [SPEC.md](https://github.com/JiDarwish/terraform-live-poll/blob/main/SPEC.md) §4.1–4.5

Blocked by nothing

## What
The first vertical slice of the poll app. FastAPI reads its config from env vars, computes `poll_id`, renders the phone vote page (question, one button per option, env badge, accent colour), stores one table entity per vote and returns counts as JSON. Runs locally with `docker compose` against Azurite. The app never creates the table, so compose needs a one-shot step that creates it.

## Acceptance criteria
- [ ] `docker compose up` → open `/` on a phone on the same network, vote, and `/api/results` shows the count go up
- [ ] Changing the question or options gives a new `poll_id` starting at zero; older votes stay in the table
- [ ] A second vote from the same phone in the same poll is refused (cookie)
- [ ] `GET /healthz` returns 200

## Verification
- [ ] `pytest app/tests` passes (poll_id stability, counting, page renders)
- [ ] `docker build --platform linux/amd64 app` succeeds; image runs as non-root on port 8000

## Files likely touched
- `app/main.py`
- `app/templates/vote.html`
- `app/static/style.css`
- `app/requirements.txt`
- `app/Dockerfile`
- `app/compose.yaml`
- `app/tests/test_app.py`

---
_Starts in `triage`. Swap `triage` for `ready` to approve it for an agent._
