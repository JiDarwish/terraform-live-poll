**Milestone:** M1 · App · **Size:** S · **Spec:** [SPEC.md](https://github.com/JiDarwish/terraform-live-poll/blob/main/SPEC.md) §4.1, §4.3

Blocked by #1

## What
`/results` is what the projector shows all day: the question, horizontal bars with counts, total votes, a QR code pointing to `/`, and a footer `env · auth mode · revision`. It refreshes every 2 s from `/api/results`. The QR is inline SVG from `segno`, built from the request host so the app never needs its own FQDN.

## Acceptance criteria
- [ ] Bars update within 2 s of a vote from a phone
- [ ] Scanning the QR on screen opens the vote page on a phone
- [ ] Footer shows env, auth mode and revision (`CONTAINER_APP_REVISION` if set, else `local`)
- [ ] Readable from the back of a meeting room (large type, high contrast)

## Verification
- [ ] `pytest app/tests` passes
- [ ] Manual: projector-size browser window, vote from a phone, watch it update

## Files likely touched
- `app/main.py`
- `app/templates/results.html`
- `app/static/results.js`
- `app/static/style.css`

---
_Starts in `triage`. Swap `triage` for `ready` to approve it for an agent._
