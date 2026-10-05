**Milestone:** M1 · App · **Size:** S · **Spec:** [SPEC.md](https://github.com/JiDarwish/terraform-live-poll/blob/main/SPEC.md) §4.4, §6

Blocked by #2, #3

## What
`app-image.yml` runs on push to `main` touching `app/**` (plus `workflow_dispatch`): run the tests, build `linux/amd64`, push `ghcr.io/jidarwish/terraform-live-poll:<git-sha>`. New GHCR packages are private by default, so the package must be made public once by hand.

## Acceptance criteria
- [ ] A merge touching `app/` publishes an image tagged with the commit SHA
- [ ] `docker pull` of that tag works without logging in (package is public)
- [ ] A failing test stops the push

## Verification
- [ ] Workflow run is green; `docker pull ghcr.io/jidarwish/terraform-live-poll:<sha>` from a logged-out shell

## Files likely touched
- `.github/workflows/app-image.yml`

## Needs a human
Make the GHCR package public once (package settings → Change visibility).

---
_Starts in `triage`. Swap `triage` for `ready` to approve it for an agent._
