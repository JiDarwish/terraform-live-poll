**Milestone:** M2 · Bootstrap · **Size:** S · **Spec:** [SPEC.md](https://github.com/JiDarwish/terraform-live-poll/blob/main/SPEC.md) §5.1

Blocked by #5

## What
A user-assigned managed identity `id-livepoll-github` with federated credentials for `repo:JiDarwish/terraform-live-poll:pull_request`, `…:ref:refs/heads/main` and `…:environment:prod`. Roles: Contributor + Role Based Access Control Administrator on `rg-livepoll-prod`, Storage Blob Data Contributor on the `tfstate` container. No Entra app registration (no tenant-admin rights needed).

## Acceptance criteria
- [ ] Exactly three federated credentials exist with the subjects above
- [ ] Role assignments are visible on the prod RG and the state container
- [ ] A code comment states the demo shortcut and the real-life least-privilege version (§5.1 talking point)

## Verification
- [ ] `terraform -chdir=bootstrap plan` → no changes; OIDC login itself is proven in #11

## Files likely touched
- `bootstrap/main.tf`
- `bootstrap/outputs.tf`

---
_Starts in `triage`. Swap `triage` for `ready` to approve it for an agent._
