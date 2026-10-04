# Plan: #1 App, vote end to end locally (key mode, Azurite)

**Before you start:**
- **Do not edit `tasks/plan.md`.** It is the committed, project-wide index of issues #1–#27, not this ticket's plan.
- **No Docker on this planning machine.** If Docker is also missing where you build, run every step except the `docker build` and `compose` checks. Then say in the PR that those checks were not run. Do not tick them.
- **Out of scope here:** `/results` with the QR code and `segno` belong to #2. Identity mode and the vote-store-down banner belong to #3. Leave clean seams for both and build neither.

## Decisions the spec left open

1. **Main design: dependency seams instead of module-level globals.** `main.py` has two FastAPI dependencies:
   - `get_settings()`: reads env vars, cached with `lru_cache`.
   - `get_table(settings)`: returns a `TableClient`, cached.

   Routes take both through `Depends`. Tests swap them with `app.dependency_overrides`: a `Settings` they build themselves, and an in-memory `FakeTable` with `create_entity` and `query_entities`. This lets you test without Azurite or env reloads, and it is the seam #3 extends for identity mode.
2. **`poll_id`:** `sha256((POLL_QUESTION + POLL_OPTIONS).encode()).hexdigest()[:8]`. It hashes the raw env strings with no separator, which is what the spec says literally. The displayed options are `[o.strip() for o in POLL_OPTIONS.split("|") if o.strip()]`.
3. **Env defaults:**
   - `POLL_QUESTION` and `POLL_OPTIONS` are required. If either is missing, fail with a clear error the first time settings load.
   - `ENVIRONMENT` defaults to `dev`, `POLL_COLOR` to `#2f7d5b`, `TABLE_NAME` to `votes`, `AUTH_MODE` to `key`.
   - Any `AUTH_MODE` other than `key` raises `ValueError("AUTH_MODE=identity arrives in #3")` inside `get_table`, not at import. `/` and `/healthz` never touch storage, so they keep working.
4. **Voting without JavaScript:**
   - `vote.html` is a `<form method="post" action="/api/vote">` with one `<button name="option" value="…">` per option. This adds a dependency on `python-multipart`.
   - On success, `POST /api/vote` sets the cookie and returns **303 → `/`**.
   - When the cookie matches the current `poll_id`, `GET /` shows "Thanks, look at the screen" and a link to **`/api/results`**. `/results` does not exist until #2, which re-points this link.
5. **Cookie:** one cookie, `voted=<poll_id>`, with `HttpOnly`, `SameSite=Lax`, `Path=/` and `max_age` of 1 day. It has no `Secure` flag because local runs are plain HTTP over the LAN.
   - If the cookie already matches the current `poll_id`, `POST /api/vote` returns **409** `{"error": "already voted"}` and writes nothing.
   - A cookie from an older poll does not match, so that phone can vote again in the new poll.
   - An option that is not in the current list returns **400**.
6. **`/api/results` JSON (a stable contract, because #2 reads it):**
   ```
   {"poll_id", "question", "environment", "options": [{"option", "count"}, ...], "total"}
   ```
   - Options come in config order, and options with no votes show 0.
   - The query is `query_entities("PartitionKey eq @pk", parameters={"pk": poll_id}, select=["option"])`.
   - The counting is `collections.Counter`.
7. **Storage failures:** in `POST /api/vote` and `GET /api/results`, catch `azure.core.exceptions.AzureError`, call `logger.exception`, and return 503 `{"error": "vote store unreachable"}`. The banner and the retry with backoff are #3's job.
8. **`/healthz`:** returns 200 `{"status": "ok"}` and never touches storage, so it is a pure liveness check.
9. **Paths:** templates and static files are found relative to `Path(__file__).parent`. Otherwise `pytest app/tests` run from the repo root cannot find them. `app/tests/conftest.py` adds `app/` to `sys.path` and holds the fakes and fixtures.
10. **Dependencies:**
    - `app/requirements.txt` holds the runtime packages only: `fastapi`, `uvicorn`, `jinja2`, `python-multipart`, `azure-data-tables`. Pin each with `==` to the current release.
    - A new `app/requirements-dev.txt` holds `-r requirements.txt`, `pytest`, `httpx`, so the image stays small.
11. **Creating the table in compose:** a one-shot `table-init` service runs the **app image itself** with `python -c "…create_table_if_not_exists(...)"`. `main.py` never creates the table.
    - `table-init` waits for `azurite` with `depends_on: service_healthy`. The health check is `nc -z 127.0.0.1 10002`. If the Azurite image has no `nc`, use `node -e` with a TCP connect instead.
    - `app` waits for `table-init` with `depends_on: service_completed_successfully`.
12. **Azurite:**
    - Run `azurite-table --tableHost 0.0.0.0 --skipApiVersionCheck`, so a newer SDK does not break against an older emulator.
    - Use a **named volume** so votes survive `docker compose down`. That makes "older votes stay in the table" visible.
    - The connection string is Azurite's public, well-known `devstoreaccount1` key with `TableEndpoint=http://azurite:10002/devstoreaccount1;`. It is safe to commit.
13. **Compose env uses `${POLL_QUESTION:-…}` style defaults.** The defaults are the example values from SPEC §4.2. To check acceptance criterion 2 without editing files, run `POLL_QUESTION="Other?" docker compose up -d app`.
14. **Image:**
    - `python:3.12-slim` with `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1`.
    - `useradd --uid 10001` and `USER 10001`. A numeric UID lets non-root checks work.
    - `EXPOSE 8000`.
    - `CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000","--proxy-headers","--forwarded-allow-ips","*"]`. The proxy flags are for Container Apps ingress and for #2's request-host QR code. They do no harm locally.
    - Copy only `main.py`, `templates/` and `static/`. Add an `app/.dockerignore` that excludes `tests/`, `__pycache__`, `.venv` and `requirements-dev.txt`.
15. **No CSS injection guard on `POLL_COLOR`.** The colour goes in as `style="--accent: {{ color }}"` with Jinja autoescape on. Terraform controls the value, and a validation regex would cost lines in the ~200-line budget.

## Tasks

### Task 1: Settings, `poll_id`, `/healthz` (XS–S)
**Files:** `app/main.py`, `app/requirements.txt`, `app/requirements-dev.txt`, `app/tests/conftest.py`, `app/tests/test_app.py`

**What:**
- In `main.py`: a frozen `Settings` dataclass (`question`, `options_raw`, `color`, `environment`, `auth_mode`, `table_name`, `connection_string`). It has an `options` property and a `poll_id` property.
- `get_settings()`, the `app = FastAPI()` object and `GET /healthz`.
- In `conftest.py`: a `make_settings(**overrides)` helper and a `client` fixture that installs the overrides.

**Tests:**
- `test_poll_id_is_stable_8_hex`: matches a `hashlib` value computed in the test, and is the same across two calls.
- `test_poll_id_changes_with_question` and `test_poll_id_changes_with_options`.
- `test_options_split_and_trimmed`.
- `test_healthz_200`.
- `test_missing_question_fails_clearly`.

**Verify:** `pip install -r app/requirements-dev.txt && pytest app/tests`.

### Task 2: Vote store: `POST /api/vote` and `GET /api/results` (S)
**Depends on:** Task 1
**Files:** `app/main.py`, `app/tests/conftest.py` (add `FakeTable`), `app/tests/test_app.py`

**What:**
- `get_table(settings)` uses `TableServiceClient.from_connection_string(...).get_table_client(table_name)` in key mode, and raises in any other mode.
- The vote handler (decision 5) calls `create_entity({"PartitionKey": poll_id, "RowKey": str(uuid4()), "option": option})`.
- The results handler returns the shape from decision 6.
- Errors are handled as in decision 7.

**Tests:**
- `test_vote_then_results_counts_up`.
- `test_entity_shape`: PartitionKey equals `poll_id`, RowKey is a valid UUID, `option` is set.
- `test_second_vote_same_poll_refused`: 409, and the count stays at 1.
- `test_new_poll_starts_at_zero_old_votes_kept`: change the settings override. Check that results are 0 and the old entity is still in `FakeTable`. Check that the old cookie does not block a vote in the new poll.
- `test_unknown_option_400`.
- `test_store_error_returns_503`: `FakeTable` raises `AzureError`.
- `test_key_mode_uses_connection_string`: monkeypatch `TableServiceClient.from_connection_string`.
- `test_non_key_auth_mode_raises`.

**Verify:** `pytest app/tests`.

### Task 3: Phone vote page (S)
**Depends on:** Task 2, because the thanks state reads the cookie
**Files:** `app/main.py` (`GET /`, `Jinja2Templates`, `StaticFiles` mounted at `/static`), `app/templates/vote.html`, `app/static/style.css`, `app/tests/test_app.py`

**What:**
- `vote.html` has a mobile viewport meta tag, the question in big type, and one large button per option in the form.
- It shows a badge with the `ENVIRONMENT` value in upper case, with class `badge-{{ environment }}`. In CSS, `.badge-dev` is orange and `.badge-prod` is green.
- `--accent` is set on `<body>`.
- When the `voted` cookie matches the current `poll_id`, the page shows the thanks state with the `/api/results` link.
- No JavaScript.

**Tests:**
- `test_page_renders`: 200, contains the question, has one `<button` per option, contains `DEV`, contains the accent colour.
- `test_page_shows_thanks_after_vote`: after a vote, the thanks text is shown and the buttons are gone.
- `test_page_renders_prod_badge`.
- `test_static_css_served`.
- `test_page_does_not_touch_storage`: `get_table` is overridden to raise, and `/` still returns 200.

**Verify:**
- `pytest app/tests`
- `wc -l app/main.py` is under about 200 lines.

### Checkpoint A, after Tasks 1–3
- [ ] `pytest app/tests` is green.
- [ ] Run a manual smoke check against Azurite if it is available: `uvicorn main:app` with env vars set. Otherwise defer this to Task 5.

### Task 4: Image (XS)
**Depends on:** Task 3
**Files:** `app/Dockerfile`, `app/.dockerignore`

**What:** the image as described in decision 14.

**Verify:**
- `docker build --platform linux/amd64 -t livepoll:dev app` succeeds.
- `docker run --rm livepoll:dev id -u` prints `10001`.
- `docker run --rm -p 8000:8000 -e POLL_QUESTION=q -e 'POLL_OPTIONS=a|b' livepoll:dev`, then `curl localhost:8000/healthz` returns 200.

### Task 5: Compose with Azurite and `table-init`, end-to-end check (S)
**Depends on:** Task 4
**Files:** `app/compose.yaml`, `README.md` (add a short "Run locally" section: `cd app && docker compose up`, then open `http://<laptop-LAN-IP>:8000/` and `pytest app/tests`)

**What:**
- Three services: `azurite`, `table-init` and `app`, set up as in decisions 11–13.
- `app` maps `"8000:8000"` on all interfaces so phones on the LAN can reach it.
- `build: .` uses `platform: linux/amd64`.

**Optional:** an integration test in `test_app.py` marked `skipif(not os.getenv("AZURITE_CONNECTION_STRING"))`. It votes through a real `TableClient` to prove the query syntax works against the emulator.

**Verify (acceptance criteria):**
1. `docker compose up` brings everything up, `table-init` exits 0, and `curl :8000/healthz` returns 200.
2. Open `/` on a phone on the same network and vote. `/api/results` shows the count go up.
3. Vote again from the same phone, or replay the cookie with `curl -b`. The response is 409, and the count does not change.
4. Run `POLL_QUESTION="Other?" docker compose up -d app`. `/api/results` shows a new `poll_id` with a total of 0. Then restore the original question: the old `poll_id` and its count come back, which shows the old votes stayed in the table.

### Checkpoint B (done)
- [ ] Every item in the acceptance criteria and verification lists of `spec/issue-1.md` is ticked, or is reported as not run because Docker is missing.
- [ ] Run `graphify update .` only if `graphify-out/` exists. It does not exist today.

## Ordering and risks
- The tasks must run strictly in order 1 → 5. Each one leaves `pytest app/tests` green.
- **Risk:** Azurite rejects the SDK's API version. The `--skipApiVersionCheck` flag mitigates it.
- **Risk:** the Azurite image has no `nc` for the health check. Fall back to the `node -e` check from decision 11.
- **Risk:** cross-building amd64 on an arm machine is slow. This is acceptable.
- **Risk:** the phone cannot reach the laptop because of a host firewall. The README notes that port 8000 must be allowed.
