# Plan: #2 App, projector results page with QR code

**Before you start:**
- **Do not edit `tasks/plan.md`.** It is the committed index of all the project's issues. It is not this ticket's plan.
- **Docker is not installed on the planning machine.** If it is also missing where you build, run every step except the `docker compose` and phone checks. Say in the PR that those checks were not run, and leave them unticked.
- **Out of scope:** identity mode, read retries with backoff, and the phone-page banner for a store that is down all belong to #3. `/results` only has to show `managed identity` in its footer. It must never call `get_table` to do that.
- **Size budget:** SPEC §4.3 asks for `main.py` under about 200 lines (it is about 165 now) and about 30 lines of JS. Keep both lean.

## Decisions the spec left open

1. **`/results` never touches storage.** The server renders the question, the option labels with empty bars, the QR code and the footer. `results.js` fills in the counts on load and then every 2 s. This works the same way as `/`: the projector page still loads when the vote store is down. The JS then shows the existing `.banner` text "Can't reach the vote store", keeps the last counts on screen and keeps polling.
2. **Getting a new revision onto an open projector tab.** Act 6 (the footer changes `key` → `managed identity`) and Act 5 (a new question) both start a new revision. The projector tab stays open all day, so a footer drawn only by the server would never change. The fix:
   - The page puts `data-poll-id` and `data-revision` on `<main>`.
   - `/api/results` gets one new key, `"revision"`. All existing keys stay unchanged.
   - When `poll_id` or `revision` in the JSON differs from the page's value, the JS calls `location.reload()`.

   One reload rule then covers the footer, the question, the option list and the colour. We rejected rebuilding all of that in JS because it would break the 30-line budget.
3. **Revision:** add a `revision: str` field to `Settings`. `get_settings()` sets it with `os.environ.get("CONTAINER_APP_REVISION") or "local"`, so an empty value also becomes `local`.
4. **Auth label:** add a `Settings.auth_label` property. It returns `"managed identity"` when `auth_mode == "identity"` and the raw `auth_mode` otherwise. The footer reads `{{ environment }} · {{ auth_label }} · {{ revision }}`, for example `dev · key · local`, using ` · ` (U+00B7) as the separator.
5. **QR URL** is `str(request.url_for("vote_page"))`, which gives `http(s)://<request host>/`.
   - The Dockerfile already runs uvicorn with `--proxy-headers --forwarded-allow-ips *`, so the scheme is `https` behind Container Apps ingress. No Dockerfile change is needed.
   - Show the same URL as plain text under the QR code, for people who can't scan it. Jinja autoescapes it.
6. **QR rendering:** a module-level helper `qr_svg(url: str) -> str` returns `segno.make_qr(url, error="m").svg_inline(scale=10, border=4, dark="#000", light="#fff", omitsize=True)`.
   - I checked this call against segno 1.6.6. The output starts with `<svg viewBox=…` and has no XML declaration and no fixed size, so CSS controls the size.
   - `border=4` is the quiet zone the QR standard asks for, which helps scanning from far away. Black on white gives the most contrast.
   - The template inserts it with `{{ qr | safe }}`. This is safe because segno only writes the URL into QR modules, never as text. **Do not pass `title=`/`desc=` containing the URL**: the Host header is untrusted input.
7. **Readability:**
   - The results page gets `<body class="results-page" style="--accent: {{ color }}">`. All projector CSS is scoped under `.results-page`, so the phone page does not change.
   - Layout: a two-column grid, with bars on the left and the QR code on the right, sized to about `min(40vh, 30vw)`.
   - Type: the question at `clamp(2.5rem, 4vw, 5rem)`, labels and counts at `clamp(1.5rem, 2.5vw, 3rem)`, the total big, and the footer small but readable (about `1.25rem`, `#444`).
   - **Labels and counts are dark text next to the bar, never on top of it.** `POLL_COLOR` is set through Terraform and could be any colour, so text on top of it could have poor contrast.
   - Bar width is `count / max(total, 1) * 100%`.
   - Show the env badge on `/results` as well. SPEC §7.4 has the presenter point at the orange badge on dev `/results`.
8. **Polling:** the JS fetches `/api/results` with `{cache: "no-store"}` and schedules the next fetch with `setTimeout(tick, 2000)` after the current one finishes, whether it succeeded or failed. This means requests never pile up. The worst-case delay is about 2 s plus one round trip, which meets the "within 2 s" criterion. Load the script with `<script src="/static/results.js" defer>`.
9. **The thanks link on the phone page now points to `/results`.** The #1 plan said #2 would change it, because `/results` did not exist yet.
10. **Dependency:** add `segno==1.6.6` (the current release) to `app/requirements.txt`. The Dockerfile already copies `static/` and `templates/`.

## Steps (in order; commit after each, with the `(#2)` suffix as in #1's commits)

### Step 1: Settings carry revision and auth label (XS)
- `app/main.py`:
  - Add `revision: str` to `Settings` as the last field.
  - Add the `auth_label` property.
  - Set `revision` in `get_settings()` (decision 3).
- `app/tests/conftest.py`: add `revision="local"` to `make_settings` defaults.
- `app/tests/test_app.py`:
  - Extend `test_settings_defaults_from_env` so it also deletes `CONTAINER_APP_REVISION` and checks `s.revision == "local"`.
  - Add `test_revision_from_env`: set the variable to `ca-livepoll--abc123`, call `cache_clear`, assert the value, then `cache_clear` again.
  - Add `test_revision_empty_falls_back_to_local`.
  - Add `test_auth_label`: `key` → `key`, `identity` → `managed identity`.
- **Verify:** `pytest app/tests` passes.

### Step 2: `/api/results` reports the revision (XS). Depends on step 1.
- `app/main.py` `results()`: add `"revision": settings.revision` to the response dict.
- Test: add `assert body["revision"] == "local"` to `test_vote_then_results_counts_up`.
- **Verify:** `pytest app/tests` passes.

### Step 3: Server-rendered `/results` page with QR code and footer (S). Depends on step 1.
- `app/requirements.txt`: add `segno==1.6.6`, then reinstall the dev requirements.
- `app/main.py`:
  - Add `import segno` and `qr_svg(url)` (decision 6).
  - Add `@app.get("/results", response_class=HTMLResponse) def results_page(request, settings=Depends(get_settings))`. It renders `results.html` with: question, options, color, environment, auth_label, revision, poll_id, `vote_url = str(request.url_for("vote_page"))` and `qr = qr_svg(vote_url)`.
  - It must have **no** `get_table` dependency.
- New `app/templates/results.html`:
  - The same `<head>` as `vote.html`.
  - Badge, `<h1>`, and a hidden `<p class="banner" role="alert" hidden>Can't reach the vote store</p>`.
  - A `<ul class="bars">` with one `<li data-option="{{ option }}">` per option. Each holds a label span, a bar element with width 0, and a count span showing `–`.
  - The total (`<span class="total-count">–</span> votes`).
  - The QR block: `{{ qr | safe }}` and the escaped `vote_url`.
  - `<footer>` with the decision 4 string.
  - `<main data-poll-id=… data-revision=…>`.
  - The `defer` script tag.
- Tests in `app/tests/test_app.py`, in a new `# --- projector results page ---` section:
  - `test_results_page_renders`: status 200, the question, every option label, `<svg`, `/static/results.js`, `DEV`, `dev · key · local`, `data-poll-id="<poll_id>"`, `data-revision="local"`.
  - `test_results_qr_uses_request_host`: monkeypatch `main.qr_svg` to record its argument. Request with `headers={"host": "poll.example.com"}`. Assert the recorded URL is `http://poll.example.com/` and that the URL text is on the page.
  - `test_qr_svg_is_inline_svg`: `qr_svg("http://x/")` starts with `<svg` and contains no `<?xml` and no `width=`.
  - `test_results_footer_identity_and_revision`: `make_settings(auth_mode="identity", revision="ca-livepoll--abc123", environment="prod")` → `prod · managed identity · ca-livepoll--abc123`. This also proves `get_table`'s `ValueError` is not hit.
  - `test_results_page_does_not_touch_storage`: copy the pattern of `test_page_does_not_touch_storage`.
  - `test_results_page_escapes_question`: a question containing `<b>x</b>` appears as `&lt;b&gt;`.
- **Verify:** `pytest app/tests` passes.

### Checkpoint A (after steps 1–3)
- `pytest app/tests` is green.
- `uvicorn main:app` from `app/`, with `POLL_QUESTION`/`POLL_OPTIONS` set and no storage, serves `/results` with a QR code and footer. Scan it with a phone camera; it should show `http://<host>/`.

### Step 4: Live refresh with `results.js` (S). Depends on steps 2 and 3.
- New `app/static/results.js`, about 30 lines, plain JS, no framework:
  - `tick()` fetches `/api/results` with `no-store`.
  - When the response is not OK or the fetch throws: show the banner and keep the old counts.
  - When it is OK:
    - Hide the banner.
    - Reload if `poll_id` or `revision` differs from `main.dataset` (decision 2).
    - Otherwise, for each `data.options` entry, set that `li`'s count text and bar `style.width`, and set the total.
  - Always finish with `setTimeout(tick, 2000)`. Call `tick()` once at load.
  - Look up rows by `data-option`, using a `Map` built once rather than CSS selectors, because option text can contain quotes.
- Test: `test_static_results_js_served` checks that `GET /static/results.js` returns 200 and the body contains `/api/results` and `2000`. pytest cannot run the JS itself; the manual check below covers it.
- **Verify:** `pytest app/tests`. Then manually: with the step 3 uvicorn running against a stub or real store, open `/results`. The counts appear. Stopping the store shows the banner and then clears it. Restarting with a different `POLL_QUESTION` reloads the tab.

### Step 5: Projector styling (S). Can be done alongside step 4 once step 3 is done.
- `app/static/style.css`: add a `.results-page` section following decision 7. This covers the wider `main`, the grid, the type scale, the bars (`background: var(--accent)`, a light grey track, `transition: width .4s`), the QR size and the footer.
- Do not change any existing rule. `test_static_css_served` and the look of the phone page must stay the same.
- Test: extend `test_static_css_served` to also assert `.results-page` is in the body.
- **Verify:** `pytest app/tests`. Then manually: open a 1920×1080 browser window, or zoom out to 50%, and read the page from 3 m away. The question, the counts and the total must be readable, and the QR code must scan from across the room.

### Step 6: Point the phone at the projector page, and update the docs (XS). Depends on step 3.
- `app/templates/vote.html`: change the thanks link `href="/api/results"` to `href="/results"`.
- `app/tests/test_app.py` `test_page_shows_thanks_after_vote`: change the assertion to `href="/results"`.
- `README.md` "Run locally": add `http://localhost:8000/results` as the projector page. Point out that the QR code uses whatever host the browser used, so open it via the LAN IP, not `localhost`, or phones can't reach it.
- **Verify:** `pytest app/tests` passes.

### Checkpoint B (done)
- `pytest app/tests` is green (the Azurite test is skipped unless `AZURITE_CONNECTION_STRING` is set).
- If Docker is available: run `cd app && docker compose up --build`. Open `http://<LAN-IP>:8000/results` in a projector-size window and scan the QR code with a phone. The vote page opens. Vote, and the bar moves within 2 s. The footer reads `dev · key · local`.
- `main.py` is still about 200 lines or fewer, and `results.js` about 30.
- Check every acceptance criterion in `spec/issue-2.md` against the evidence above. Tick only the ones that were really checked.

## Risks
| Risk | Impact | Mitigation |
|---|---|---|
| An open projector tab never shows a new footer or question | High (the Act 6 and Act 5 beats are lost) | Decision 2: reload when the revision or poll changes, plus the `revision` key in the JSON |
| The QR code encodes `localhost` when the presenter opens `/results` locally | Med (phones fail locally) | README note (step 6). In Azure the host is the public FQDN |
| The QR code encodes `http` behind TLS ingress | Low | The Dockerfile already trusts proxy headers. Check `https` in M3 |
| Text on top of an arbitrary `POLL_COLOR` has poor contrast | Med | Labels and counts never sit on top of the bar (decision 7) |
| Injection through the Host header | Low | The URL goes into QR modules and autoescaped text only. Never into an SVG `title` |
