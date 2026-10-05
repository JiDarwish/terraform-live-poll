**Milestone:** M1 · App · **Size:** S · **Spec:** [SPEC.md](https://github.com/JiDarwish/terraform-live-poll/blob/main/SPEC.md) §4.3

Blocked by #1

## What
The one image must support both auth modes, so no app release happens during the session. `AUTH_MODE=identity` uses `ManagedIdentityCredential(client_id=AZURE_CLIENT_ID)` against `https://{account}.table.core.windows.net`. If the store is unreachable, pages still render with a banner and the server logs the cause. Reads retry with backoff (covers slow role propagation).

## Acceptance criteria
- [ ] Unit tests prove `AUTH_MODE=key` and `AUTH_MODE=identity` each build the right client (mocked)
- [ ] With Azurite stopped, `/` and `/results` render with the banner "Can't reach the vote store"; the log shows why
- [ ] `app/main.py` stays under about 200 lines

## Verification
- [ ] `pytest app/tests` passes
- [ ] Manual: `docker compose stop azurite`, reload both pages

## Files likely touched
- `app/main.py`
- `app/templates/*.html`
- `app/tests/test_auth.py`

---
_Starts in `triage`. Swap `triage` for `ready` to approve it for an agent._
