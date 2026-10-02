# Implementation plan: Live Poll

## Overview
Build the live-poll Terraform demo described in [SPEC.md](../SPEC.md): a FastAPI poll app on Azure Container Apps, a bootstrap layer (state, identities, GitHub environment), an app-team root module for dev and prod, a data-platform root module that takes over the vote store mid-session, GitHub Actions for plan/apply/drift, prepared scenario branches, a reset script and a runbook Fokke can present from alone.

## Where the tasks live
**Tasks are tracked as GitHub issues in [JiDarwish/terraform-live-poll](https://github.com/JiDarwish/terraform-live-poll/issues)**, one per task, task N = issue #N. This file is the ordered index; the issue is the source of truth for acceptance criteria.

**Triage gate:** every issue starts with the `triage` label. Swap it for `ready` to approve it. An agent only picks up issues labelled `ready` whose "Blocked by" issues are closed.

## Architecture decisions
All decisions are in SPEC.md §2 (D1–D17). The ones that shape the task order:
- **Vertical slices.** The app is usable on a phone after #1; dev works end to end after #9; prod works through CI after #12.
- **Riskiest assumption first.** #10 tests key auth off + managed identity on dev before any scenario branch depends on it.
- **Scenario branches are stacked** (`act4-prevent-destroy` → `act5` → `act6` → `act7`) and rebased onto the final `session-start` tag in #25.
- **`session-start` is cut last** (#25), because `reset.sh` force-pushes it to `main`: anything not in the tag is lost at reset.

## Task list

### M1 · App
_Done when:_ `docker compose up` → vote on a phone over the LAN, results update within 2 s. Tests pass. Key mode works against Azurite; identity mode unit-tested here, proven against Azure in M3.

- [ ] [#1](https://github.com/JiDarwish/terraform-live-poll/issues/1) App: vote end to end locally (key mode, Azurite) · `app` · M · blocked by —
- [ ] [#2](https://github.com/JiDarwish/terraform-live-poll/issues/2) App: projector results page with QR code · `app` · S · blocked by [#1](https://github.com/JiDarwish/terraform-live-poll/issues/1)
- [ ] [#3](https://github.com/JiDarwish/terraform-live-poll/issues/3) App: managed identity mode and vote-store-down banner · `app` · S · blocked by [#1](https://github.com/JiDarwish/terraform-live-poll/issues/1)
- [ ] [#4](https://github.com/JiDarwish/terraform-live-poll/issues/4) CI: build and publish the app image to GHCR · `ci` · S · blocked by [#2](https://github.com/JiDarwish/terraform-live-poll/issues/2), [#3](https://github.com/JiDarwish/terraform-live-poll/issues/3)

### M2 · Bootstrap
_Done when:_ Bootstrap applied, its state migrated, GitHub environment and variables exist, Fokke can `init` dev.

- [ ] [#5](https://github.com/JiDarwish/terraform-live-poll/issues/5) Bootstrap: state storage, resource groups and presenter access · `infra` · M · blocked by —
- [ ] [#6](https://github.com/JiDarwish/terraform-live-poll/issues/6) Bootstrap: CI identity with OIDC federation · `infra` · S · blocked by [#5](https://github.com/JiDarwish/terraform-live-poll/issues/5)
- [ ] [#7](https://github.com/JiDarwish/terraform-live-poll/issues/7) Bootstrap: GitHub environment and Actions variables · `infra` · S · blocked by [#6](https://github.com/JiDarwish/terraform-live-poll/issues/6)

### M3 · infra on dev
_Done when:_ Apply from the laptop → working dev URL. `state pull` shows the key. Key-auth-off behaviour known (§12 #3, #4).

- [ ] [#8](https://github.com/JiDarwish/terraform-live-poll/issues/8) infra: vote store on dev · `infra` · M · blocked by [#5](https://github.com/JiDarwish/terraform-live-poll/issues/5)
- [ ] [#9](https://github.com/JiDarwish/terraform-live-poll/issues/9) infra: poll app running on dev · `infra` · M · blocked by [#4](https://github.com/JiDarwish/terraform-live-poll/issues/4), [#8](https://github.com/JiDarwish/terraform-live-poll/issues/8)
- [ ] [#10](https://github.com/JiDarwish/terraform-live-poll/issues/10) Spike: key auth off and managed identity on dev · `infra` · S · blocked by [#3](https://github.com/JiDarwish/terraform-live-poll/issues/3), [#9](https://github.com/JiDarwish/terraform-live-poll/issues/9)

### M4 · Workflows + prod
_Done when:_ A PR shows a plan comment. Merge → approval → prod URL works. Drift workflow goes red on a portal edit and opens an issue.

- [ ] [#11](https://github.com/JiDarwish/terraform-live-poll/issues/11) CI: plan on pull request with a readable plan comment · `ci` · M · blocked by [#7](https://github.com/JiDarwish/terraform-live-poll/issues/7), [#8](https://github.com/JiDarwish/terraform-live-poll/issues/8)
- [ ] [#12](https://github.com/JiDarwish/terraform-live-poll/issues/12) CI: approved apply to prod and first prod deploy · `ci` · M · blocked by [#9](https://github.com/JiDarwish/terraform-live-poll/issues/9), [#11](https://github.com/JiDarwish/terraform-live-poll/issues/11)
- [ ] [#13](https://github.com/JiDarwish/terraform-live-poll/issues/13) CI: scheduled drift detection that opens an issue · `ci` · S · blocked by [#12](https://github.com/JiDarwish/terraform-live-poll/issues/12)
- [ ] [#14](https://github.com/JiDarwish/terraform-live-poll/issues/14) data-platform: skeleton root module and its workflows · `infra` · S · blocked by [#13](https://github.com/JiDarwish/terraform-live-poll/issues/13)

### M5 · Scenario branches
_Done when:_ Every branch in SPEC §7.3 gives the plan its act expects.

- [ ] [#15](https://github.com/JiDarwish/terraform-live-poll/issues/15) Scenario branches for Act 4 (replication, table rename, prevent_destroy) · `infra` · S · blocked by [#12](https://github.com/JiDarwish/terraform-live-poll/issues/12)
- [ ] [#16](https://github.com/JiDarwish/terraform-live-poll/issues/16) Scenario branch for Act 5 (ignore_changes) and drift rehearsal · `infra` · S · blocked by [#13](https://github.com/JiDarwish/terraform-live-poll/issues/13), [#15](https://github.com/JiDarwish/terraform-live-poll/issues/15)
- [ ] [#17](https://github.com/JiDarwish/terraform-live-poll/issues/17) Scenario branch for Act 6 (managed identity, key auth off) · `infra` · S · blocked by [#10](https://github.com/JiDarwish/terraform-live-poll/issues/10), [#16](https://github.com/JiDarwish/terraform-live-poll/issues/16)

### M6 · Handover
_Done when:_ Act 7 on dev and prod: the votes survive, and nothing is destroyed in any plan.

- [ ] [#18](https://github.com/JiDarwish/terraform-live-poll/issues/18) Act 7, data team side: import the vote store · `infra` · M · blocked by [#14](https://github.com/JiDarwish/terraform-live-poll/issues/14), [#17](https://github.com/JiDarwish/terraform-live-poll/issues/17)
- [ ] [#19](https://github.com/JiDarwish/terraform-live-poll/issues/19) Act 7, app team side: release, data sources and prod handover · `infra` · M · blocked by [#18](https://github.com/JiDarwish/terraform-live-poll/issues/18)

### M7 · Reset
_Done when:_ `scripts/reset.sh` runs from Fokke's laptop and gets back to SPEC §7.1.

- [ ] [#20](https://github.com/JiDarwish/terraform-live-poll/issues/20) scripts/reset.sh: back to session start in one command · `infra` · S · blocked by [#19](https://github.com/JiDarwish/terraform-live-poll/issues/19)

### M8 · Runbook
_Done when:_ Fokke can run the whole session alone from RUNBOOK.md, with fallback scripts for every 'other person' step.

- [ ] [#21](https://github.com/JiDarwish/terraform-live-poll/issues/21) scenarios/: fallback scripts for every 'other person' step · `runbook` · S · blocked by [#13](https://github.com/JiDarwish/terraform-live-poll/issues/13), [#17](https://github.com/JiDarwish/terraform-live-poll/issues/17)
- [ ] [#22](https://github.com/JiDarwish/terraform-live-poll/issues/22) RUNBOOK.md part 1: setup, morning-of checklist, Acts 1–3 · `runbook` · M · blocked by [#12](https://github.com/JiDarwish/terraform-live-poll/issues/12), [#21](https://github.com/JiDarwish/terraform-live-poll/issues/21)
- [ ] [#23](https://github.com/JiDarwish/terraform-live-poll/issues/23) RUNBOOK.md part 2: Acts 4–7, cut order and closing · `runbook` · M · blocked by [#19](https://github.com/JiDarwish/terraform-live-poll/issues/19), [#22](https://github.com/JiDarwish/terraform-live-poll/issues/22)
- [ ] [#24](https://github.com/JiDarwish/terraform-live-poll/issues/24) README and presenter laptop setup · `runbook` · S · blocked by [#14](https://github.com/JiDarwish/terraform-live-poll/issues/14)

### M9 · Rehearsal
_Done when:_ All acts timed, §11 decided, fallback recordings captured, Fokke ran it solo.

- [ ] [#25](https://github.com/JiDarwish/terraform-live-poll/issues/25) Cut the session-start tag and rebase the scenario branches · `infra` · S · blocked by [#20](https://github.com/JiDarwish/terraform-live-poll/issues/20), [#23](https://github.com/JiDarwish/terraform-live-poll/issues/23), [#24](https://github.com/JiDarwish/terraform-live-poll/issues/24)
- [ ] [#26](https://github.com/JiDarwish/terraform-live-poll/issues/26) Full rehearsal and the §11 decisions · `runbook` · M · blocked by [#25](https://github.com/JiDarwish/terraform-live-poll/issues/25)
- [ ] [#27](https://github.com/JiDarwish/terraform-live-poll/issues/27) Solo rehearsal by Fokke and fallback recordings · `runbook` · M · blocked by [#26](https://github.com/JiDarwish/terraform-live-poll/issues/26)

## Checkpoints

### After M1 (#1–#4)
- [ ] App runs locally and on a phone
- [ ] Image is public on GHCR

### After M3 (#5–#10)
- [ ] Dev works end to end from the laptop
- [ ] Spike #10 outcome known — **review with Ji: does Act 6/7 wording change?**

### After M4 (#11–#14)
- [ ] A question change goes PR → approval → phones
- [ ] Drift workflow goes red on a portal edit

### After M6 (#15–#19)
- [ ] Every scenario branch behaves as in §7.3
- [ ] Handover done on prod with votes intact

### Done (#20–#27)
- [ ] Reset works from Fokke's laptop
- [ ] Fokke ran the session solo (definition of done)

## Dependency graph (critical path in bold)

```
#1 app slice ─┬─ #2 results ─┐
              └─ #3 identity ┴─ #4 image ─┐
#5 bootstrap state ─┬─ #6 CI identity ─ #7 GitHub env ─┐
                    └─ #8 vote store ─────────────┬────┴─ #11 PR plan
                                     #4 ─ #9 app on dev ─┤
                                     #3 ─ #10 spike ─────┤
**#9 + #11 → #12 prod apply → #13 drift → #14 data-platform skeleton**
#12 → #15 act4 → #16 act5 → #17 act6 (+#10) → #18 act7 data → #19 act7 app → #20 reset
#13,#17 → #21 scenarios → #22 runbook 1 → #23 runbook 2 (+#19)
#14 → #24 README
**#20 + #23 + #24 → #25 tag → #26 rehearsal → #27 Fokke solo**
```

## Parallel work
- #2 and #3 in parallel after #1.
- #5–#7 (bootstrap) in parallel with all of M1.
- #24 (README) and #21 (scenario scripts) in parallel with M5–M6.
- Everything from #15 to #19 is sequential (stacked branches, one shared dev and prod).

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| azurerm 5.x arguments differ from what the spec assumes | Med | Check every argument against the 5.8 docs (#8, #9, #18); SPEC §12 lists the known unknowns |
| Key still/no longer in state when key auth is off | High (changes Act 6/7 wording) | Spike #10 before any branch work; checkpoint review with Ji |
| Container Apps environment is slow to create | Med (Act 1 stalls) | Measured in #9; §11 rule moves it to bootstrap if over 4 min |
| Role assignment propagation (up to 30 min) | High (Act 6 breaks live) | App identity + role exist from day one; `reset.sh` runs the day before |
| Required reviewers not available on GitHub Free | High (no approval gate) | Confirmed in #7, early; fallback is GitHub Pro |
| Work committed to `main` after the tag is wiped by reset | Med | Tag cut last (#25); README warns about it |
| Public repo exposes something sensitive | Low | No secrets anywhere (OIDC); state never in git; `.gitignore` from day one |

## Open questions
- Fokke's Entra object id and GitHub username (needed by #5 and #7).
- Where the fallback recordings are stored (#27).
