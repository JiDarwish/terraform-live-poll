# Plan: #3 App, managed identity mode and vote-store-down banner

**Before you start:**
- **Do not edit `tasks/plan.md`.** It is the committed index of all the project's issues, not this ticket's plan.
- **Docker is not installed on the planning machine.** If it is also missing where you build, run every step except the `docker compose stop azurite` check. Say in the PR that this check was not run, and leave its box unticked.
- **Size budget:** `app/main.py` is **191 lines now**. This ticket adds about 20 lines. The hard ceiling is **205 lines (`wc -l app/main.py`)** and the aim is about 200. That is why Step 1 is a refactor that only frees up lines.
- **Commits:** one per step, with the `(#3)` suffix, as in #1 and #2 (for example `app: build the identity-mode table client (#3)`).
- Baseline: `pytest app/tests` → 32 passed, 1 skipped.

## Decisions the spec left open

1. **`/` reads the store. `/results` still does not.**
   - Today `GET /` never touches storage, so with Azurite stopped it shows no banner. That fails the acceptance criterion.
   - The phone page has no JS (`test_page_renders` asserts `<script` is absent), so the server must check. `vote_page` will do the same partition read that `/api/results` does. If it gets `AzureError`, it logs the error and renders with `store_down=True`.
   - **The status stays 200.** The page did render. The 503 stays only on a failed form POST, where the vote really was lost.
   - The buttons stay visible, so a phone can retry once the store is back.
   - `/results` keeps #2's design (decision 1 there). It is server-rendered with no storage access, and `results.js` already un-hides `.banner` when `/api/results` fails. Keep `test_results_page_does_not_touch_storage`.
   - `test_page_does_not_touch_storage` (`test_app.py:242`) is now wrong by design. Replace it in Step 4.
2. **Retries come from the SDK's retry policy, not a hand-written loop.** Add one module-level constant:
   ```python
   # Reads retry with backoff (0 s, 1 s, 2 s), 403 included: a new role assignment can take minutes to propagate.
   RETRY = dict(retry_total=3, retry_backoff_factor=0.5, retry_on_status_codes=[403])
   ```
   Pass it as `**RETRY` to both client constructors. I checked this against azure-data-tables 12.7.0 and azure-core 1.41.0 using a fake transport:
   - A GET that keeps getting 403 makes 4 attempts and sleeps `[1.0, 2.0]`, about 3 s in total.
   - **A POST (`create_entity`) gets 403 once and is not retried.** azure-core's method allowlist leaves out POST. So reads retry and writes do not, exactly as the spec says, with no extra code.
   - An unreachable endpoint fails with `ServiceRequestError` after about 3.0 s. The SDK default takes about 4.8 s.

   **Why:** it costs about 3 lines against the budget, where a loop would cost about 10. It also caps how long a phone's `/` load waits when the store is down. A loop around the SDK would stack on top of the SDK's own default retries.
3. **The log message is one line, and it gives the cause.** Replace `logger.exception("vote store unreachable")` (now in 2 places) with one helper, `log_store_down(exc)`. It calls `logger.error("vote store unreachable: %s: %s", type(exc).__name__, exc)`.
   - **Why:** with the store down, the projector hits `/api/results` every 2 s, plus `/` on every phone. A full Azure traceback each time would bury the cause in `docker compose logs`.
   - The exception type and message are the "why" (for example `ServiceRequestError: … Failed to resolve 'azurite'`, or `ClientAuthenticationError` / `HttpResponseError … AuthorizationPermissionMismatch`).
4. **The `Settings` dataclass gets two plain fields: `account_name` (`STORAGE_ACCOUNT_NAME`) and `client_id` (`AZURE_CLIENT_ID`).** Both are read with `os.environ.get(..., "")`, like `connection_string`. They have no defaults in the dataclass. Add them to `make_settings` in `conftest.py`, the only other place that builds `Settings`.
   - **Neither mode checks for missing variables.** An empty account name or client id fails when the app first talks to the store, and the banner plus the log line show the cause. It is not worth extra lines. #10 checks the real wiring on Azure.
5. **An unknown `AUTH_MODE` still raises `ValueError` in `get_table`.** The message changes from `arrives in #3` to `AUTH_MODE must be key or identity, got {mode!r}`.
6. **Dependency:** add `azure-identity==1.26.0` (the current release) to `app/requirements.txt`. Import `ManagedIdentityCredential` at module level. Building it makes no network call, so tests can construct it, but they still patch it out.
7. **Test file:** create `app/tests/test_auth.py`, as the spec asks. Move the two existing auth tests out of `test_app.py` into it (`test_key_mode_uses_connection_string` and `test_non_key_auth_mode_raises`).

## Steps (in order; each one leaves `pytest app/tests` green)

### Step 1: Share the page context between the two pages (XS, refactor only)
- **`app/main.py`:** `render_vote_page` and `results_page` both pass `question`, `options`, `color` and `environment`. Pull those four keys out into one small helper, for example `page_context(settings) -> dict`, and merge it in each place with `{**page_context(settings), ...}`. Templates and behaviour do not change.
- **Proof:** `pytest app/tests` gives the same result as the baseline. `wc -l app/main.py` goes down by about 4 or 5 lines.
- **Ordering:** this must come first, to make room for Steps 2–4.

### Step 2: Identity mode builds the right client (S)
- **`app/requirements.txt`:** add `azure-identity==1.26.0`.
- **`app/main.py`:**
  - Add `from azure.identity import ManagedIdentityCredential`.
  - Add the two `Settings` fields and read them in `get_settings()` (decision 4).
  - Add the `RETRY` constant (decision 2).
  - Rewrite `get_table`. For `key`, use `TableServiceClient.from_connection_string(settings.connection_string, **RETRY)`. For `identity`, use `TableServiceClient(f"https://{settings.account_name}.table.core.windows.net", credential=ManagedIdentityCredential(client_id=settings.client_id), **RETRY)`. Anything else raises `ValueError` (decision 5). Both modes end with `service.get_table_client(settings.table_name)`. Keep `@lru_cache` and the "the app never creates the table" comment.
- **`app/tests/conftest.py`:** add `account_name=""` and `client_id=""` to `make_settings`.
- **`app/tests/test_auth.py`** (new). Use `main.get_table.cache_clear()` around each call, as the existing test does:
  - `test_key_mode_uses_connection_string`: moved from `test_app.py`. Extend it so the fake `from_connection_string(conn_str, **kwargs)` also records kwargs, and assert `kwargs == main.RETRY`.
  - `test_identity_mode_uses_managed_identity`:
    - Monkeypatch `main.ManagedIdentityCredential` with a fake that records `client_id`.
    - Monkeypatch `main.TableServiceClient` with a fake class that records `(endpoint, credential, kwargs)` and has `get_table_client`.
    - Then assert three things: the endpoint is `https://stlivepolldevxx01.table.core.windows.net`, the credential is the fake built with `client_id="cid"`, and the kwargs equal `main.RETRY`.
    - Also assert that `from_connection_string` was **not** called.
  - `test_unknown_auth_mode_raises`: replaces `test_non_key_auth_mode_raises`, using `match="AUTH_MODE"`.
  - `test_identity_settings_from_env`: set `AUTH_MODE=identity`, `STORAGE_ACCOUNT_NAME` and `AZURE_CLIENT_ID`, then check that `get_settings()` carries them through. Clear the cache before and after, like `test_settings_defaults_from_env`.
  - `test_reads_retry_403_with_backoff_writes_do_not`:
    - Build a real client with `TableServiceClient.from_connection_string(<Azurite dev conn string>, transport=FakeTransport(), **main.RETRY)`.
    - `FakeTransport` subclasses `azure.core.pipeline.transport.HttpTransport` and records each `request.method`. It always returns a 403, built as `RequestsTransportResponse(request, requests_response)` where `requests_response` is a `requests.Response` with `status_code=403`, a JSON `odata.error` body and `Content-Type: application/json`. `requests` is already installed as an azure-core dependency.
    - Use `monkeypatch.setattr("time.sleep", slept.append)` so the test runs instantly.
    - Assert that `query_entities` makes 4 GETs, records sleeps of `[1.0, 2.0]` and raises `HttpResponseError`. Assert that `create_entity` makes exactly 1 POST.
    - This test proves decision 2. It is about 20 lines. If the azure-core response class turns out to be awkward, keep the test and adapt the fake. Do not drop it.
- **`app/tests/test_app.py`:** delete the two moved tests.
- **Proof:** `pytest app/tests` passes, including the new `test_auth.py`.

### Step 3: One-line cause in the log, one read helper (XS)
- **`app/main.py`:**
  - Replace `store_unreachable()` with `log_store_down(exc)` (decision 3) plus a 503 JSON response. Either have `store_unreachable(exc)` call `log_store_down` and return the `JSONResponse`, or inline it, whichever reads shorter.
  - In `vote`, catch `except AzureError as exc:` and log once through the helper in both branches. That removes the extra `logger.exception` line inside the HTML branch.
  - Pull the partition query out into `count_votes(settings, table) -> Counter`. `/api/results` uses it now, and `/` uses it in Step 4.
- **Tests (`test_app.py`):** extend `test_store_error_returns_503` and `test_store_error_on_form_post_renders_banner` with `caplog`. Assert that `"vote store unreachable: AzureError: boom"` appears in `caplog.text` for both `/api/vote` and `/api/results`.
- **Proof:** `pytest app/tests`.

### Step 4: The phone page shows the banner when the store is down (S)
- **Depends on:** Step 3 (`count_votes`, `log_store_down`).
- **`app/main.py`:**
  - `vote_page` gains `table: TableClient = Depends(get_table)` and calls `count_votes(settings, table)` inside `try`. On `AzureError`, it calls `log_store_down(exc)` and sets `store_down=True`. It always returns `render_vote_page(request, settings, store_down=store_down)` with status 200.
  - Replace the comment "Never touches storage…" with one that says why the page reads: the phone sees the banner before it taps. Keep the comment on `results_page` that says it never touches storage.
- **`app/templates/vote.html`:** no change needed. The `{% if store_down %}` banner already exists from #1. `results.html` and `results.js` already have the hidden banner and un-hide it. Touch the templates only if a test shows a gap.
- **Tests (`test_app.py`):**
  - Replace `test_page_does_not_touch_storage` with `test_page_shows_banner_when_store_down`:
    - Set `table.error = AzureError("boom")`.
    - `GET /` returns 200 and the page contains `Can't reach the vote store`.
    - `html.count("<button")` still equals the number of options.
    - `caplog` contains `boom`.
    - `/healthz` is still 200, with `get_table` overridden to raise `RuntimeError`, as the old test did.
  - Extend `test_page_renders` to assert that the banner text is absent while the store is up.
  - Add `test_results_page_has_banner_for_js`:
    - `/results` returns 200 while `table.error` is set, and its HTML contains `Can't reach the vote store` inside an element with the `hidden` attribute.
    - `/static/results.js` contains `banner.hidden = false`.
    - This is the server-side half of the acceptance criterion for `/results`.
- **Proof:** `pytest app/tests`, and `wc -l app/main.py` ≤ 205. If it is over, trim the wording of comments, never their meaning, before moving on.

### Checkpoint (after Step 4)
- [ ] `pytest app/tests` passes. `test_auth.py` covers key, identity and an unknown mode, plus reads retrying while writes do not.
- [ ] `wc -l app/main.py` ≤ 205.
- [ ] `grep -n "arrives in #3" app/main.py` finds nothing.

### Step 5: Docs and manual check (XS)
- **`README.md`**, under "Run locally": add 2–3 lines.
  - `docker compose stop azurite` → `/` and `/results` show "Can't reach the vote store", and `docker compose logs app` shows `vote store unreachable: <cause>`. `docker compose start azurite` recovers.
  - Identity mode needs `AUTH_MODE=identity`, `STORAGE_ACCOUNT_NAME` and `AZURE_CLIENT_ID`. It only works on Azure, since Azurite has no managed identity.
- **Do not change `compose.yaml`.** Local runs stay in key mode.
- **Manual check (needs Docker):**
  - Run `cd app && docker compose up --build`, vote once, then `docker compose stop azurite`.
  - Reload `/`: the banner shows after about 3 s and the buttons are still there.
  - Open `/results`: the banner shows within one or two refresh cycles and the last counts stay on screen.
  - `docker compose logs app` shows one `vote store unreachable: …` line per failed read, with no traceback flood.
  - `docker compose start azurite`: the banners clear on the next refresh or reload.
  - Also check that the line reaches the logs at all. `livepoll` has no handler, so it depends on Python's last-resort stderr handler, as in #1. If it does not show up, add `logging.basicConfig(level=logging.INFO)` (one line) and say so in the PR.
- **Proof:** README renders correctly. The manual check is either ticked, or reported as not run because Docker is missing.

## Risks
| Risk | Impact | Mitigation |
|---|---|---|
| `/` now waits up to about 3 s when the store is down, because of the retries | Low: only while the store is down | The retry budget is capped by `RETRY`. The phone still gets a page with a banner. |
| During role propagation (Act 6), `/` and `/api/results` keep failing for minutes, longer than one request's 3 s of retries | Medium on stage | SPEC §5 creates the role assignment the day before. The projector keeps polling, keeps the last counts and recovers on its own. Retries only smooth over short gaps. |
| `azure-identity` pulls in `msal` and `cryptography`, so the image grows | Low | Wheels exist for linux/amd64 and Python 3.12. The CI image build (#4) will catch any problem. |
| The retry test depends on azure-core transport internals | Low | Pinned versions. It also documents the behaviour that decision 2 relies on. |

## Out of scope
- Proving identity mode against real Azure. That is #10.
- Terraform wiring of the new env vars. That is #9 and the Act 6 branch.
- Any change to `results.js`.
