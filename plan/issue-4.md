# Plan: #4 CI, build and publish the app image to GHCR

**Before you start:**
- **Do not edit `tasks/plan.md`.** It is the committed index of every issue in the project, not this ticket's plan.
- The blockers are on `main`: #2 (results page) and #3 (identity mode and banner). There is no `.github/` directory yet, so this ticket creates it.
- **The planning machine has no Docker, no `actionlint` and no `pytest`.** Real proof that the workflow works only exists after merge, on GitHub (see Step 3). Before merge, the proof is static checks plus a local run of the test suite.
- **Commits:** one commit, with the `(#4)` suffix, like the earlier tickets. For example: `ci: build and publish the app image to GHCR (#4)`.
- Expected test baseline: `pytest app/tests` → all pass, with 1 skip (the optional Azurite test).

## Decisions the spec left open

1. **Two jobs: `test`, then `image` with `needs: test`.** This is how "a failing test stops the push" is enforced: the push lives in a job that cannot start if `test` is red. It is also easy to point at on screen. Two jobs also let each job keep its own minimal `permissions:`, as §6 asks:
   - `test` gets `contents: read`.
   - `image` gets `contents: read` and `packages: write`.
   - Put `permissions: {}` at the top level of the workflow.
2. **The image name is written out in lowercase, not built from `github.repository`.** Set `env: IMAGE: ghcr.io/jidarwish/terraform-live-poll` at workflow level. `github.repository` is `JiDarwish/terraform-live-poll`, and GHCR rejects uppercase. Lowercasing it in a shell step costs lines and is harder to read on screen.
3. **One tag only: the full 40-character `${{ github.sha }}`.** There is no `latest` tag and no short SHA:
   - Terraform pins `var.app_image_tag` (#9). A moving `latest` tag would weaken the "pinned and reproducible" story.
   - The full SHA is what `git log` and the Actions UI show, so #9's tfvars can copy it directly.
   - Do not use `docker/metadata-action`. One literal tag does not need it.
4. **Triggers:**
   - `push` to `main` with `paths: ['app/**', '.github/workflows/app-image.yml']`, plus `workflow_dispatch`.
   - **The workflow file is in the paths list on purpose.** A change to the build gets exercised on merge. Without it, merging this ticket would not trigger a run at all.
   - There is no `pull_request` trigger. The §6 table does not list one, so it is out of scope.
5. **Pin actions to their current major tags, not to commit SHAs.** The YAML is shown to the room, and tags are readable. Current majors (checked 2026-10-05):

   | Action | Version |
   |---|---|
   | `actions/checkout` | `@v7` |
   | `actions/setup-python` | `@v7` |
   | `docker/setup-buildx-action` | `@v4` |
   | `docker/login-action` | `@v4` |
   | `docker/build-push-action` | `@v7` |

   Re-check these before writing the file. If a newer major has shipped, use it.
6. **Log in with `GITHUB_TOKEN`** (`registry: ghcr.io`, `username: ${{ github.actor }}`, `password: ${{ secrets.GITHUB_TOKEN }}`). No PAT and no repo secret are needed.
7. **Labels:** set `org.opencontainers.image.source=https://github.com/${{ github.repository }}` and `org.opencontainers.image.revision=${{ github.sha }}` in `build-push-action`'s `labels:`. The source label links the package to the repo, so the package shows up on the repo page and inherits its Actions access. Leave the provenance setting at its default; Container Apps handles the resulting OCI index.
8. **No build cache and no `concurrency:` block.** SHA tags never collide, and builds are rare (§4.4: no app release during the session). This is not worth the extra YAML.
9. **No README change.** The spec scopes this ticket to the workflow file. The human step goes in the PR description (Step 3).

## Steps

### Step 1: Write `.github/workflows/app-image.yml` (S)

**Workflow level:** `name: app-image`, the triggers (decision 4), `permissions: {}` and `env.IMAGE`.

**Job `test`** (`runs-on: ubuntu-latest`, `permissions: contents: read`):
1. `actions/checkout`
2. `actions/setup-python` with `python-version: "3.12"` (D15, the same as the Dockerfile base), `cache: pip` and `cache-dependency-path: app/requirements-dev.txt`
3. `pip install -r app/requirements-dev.txt`
4. `pytest app/tests`

Leave `AZURITE_CONNECTION_STRING` unset so the Azurite test skips.

**Job `image`** (`needs: test`, `runs-on: ubuntu-latest`, `permissions: contents: read, packages: write`):
1. `actions/checkout`. This is required because `context: app` is a path context, not the default git context.
2. `docker/setup-buildx-action`
3. `docker/login-action` (decision 6)
4. `docker/build-push-action` with:
   - `context: app` (it uses `app/Dockerfile` and `app/.dockerignore`)
   - `platforms: linux/amd64`
   - `push: true`
   - `tags: ${{ env.IMAGE }}:${{ github.sha }}`
   - the labels from decision 7

Add a short comment on top of `needs: test`: "a red test job means no push". Add one more next to the IMAGE env: "GHCR needs lowercase".

**Proof:**
- `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/app-image.yml'))"` parses.
- `actionlint` reports nothing. Download v1.7.12 from `rhysd/actionlint` releases into `/tmp`, or use `go run github.com/rhysd/actionlint/cmd/actionlint@latest`.
- `pip install -r app/requirements-dev.txt && pytest app/tests` is green locally. This is the same command the `test` job runs.
- If Docker is available: `docker buildx build --platform linux/amd64 app` succeeds. If it is not, say so in the PR.

### Step 2: Self-review against the acceptance criteria (XS, no file changes)

Check each item with grep or by reading the file:
- [ ] There is a push step only in `image`, and `image` has `needs: test`.
- [ ] The tag is exactly `ghcr.io/jidarwish/terraform-live-poll:${{ github.sha }}`.
- [ ] `platforms` is exactly `linux/amd64`.
- [ ] No job has more permissions than decision 1 lists.
- [ ] The triggers match decision 4.

### Step 3: Open the PR with the post-merge checklist (depends on Steps 1 and 2)

The acceptance criteria can only be proven after merge, and one of them needs a human. Put this checklist in the PR body, unticked, for the operator:
1. After merge, the `app-image` run on `main` is green. Merging this PR triggers it through the workflow-file path, or use `workflow_dispatch`.
2. **Human, once:** go to github.com/users/JiDarwish/packages/container/terraform-live-poll/settings, then **Change visibility → Public**.
3. From a logged-out shell (`docker logout ghcr.io`): `docker pull ghcr.io/jidarwish/terraform-live-poll:<merge-sha>` works.
4. **Failing test stops the push.** On a scratch branch, add a test that always fails (`assert False`), then run `gh workflow run app-image.yml --ref <scratch-branch>`. Expect a red `test` job, a skipped `image` job, and no new tag for that SHA in the package. Delete the branch afterwards. This works only once the workflow exists on `main`, because `workflow_dispatch` needs the file on the default branch.

Do not tick the acceptance-criteria boxes in the PR. They depend on items 1–4.

## Ordering

Step 1 → Step 2 → Step 3, in that order. Nothing here can run in parallel.

## Risks

| Risk | Mitigation |
|---|---|
| The first push to GHCR fails with `denied`, for example because a package with this name already exists unlinked, or Actions has no access to it | In package settings → Manage Actions access, add the repo with Write. The `image.source` label (decision 7) usually avoids this. Note it in the PR as a fallback. |
| The package stays private, so #9's Container App cannot pull the image without credentials | Post-merge item 2 is an explicit human step. #9 should not start until item 3 passes. |
| A tests job that works locally fails in CI because of Python 3.13 versus 3.12 | CI pins 3.12, the same as the Dockerfile. If a local 3.13 run differs, CI is the authority. |
