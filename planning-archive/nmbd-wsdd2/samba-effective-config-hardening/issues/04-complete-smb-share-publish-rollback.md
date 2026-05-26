# Complete SMB Share Publish Rollback

## What to build

Complete rollback behavior for SimpleSaferServer-owned shares file publishes. If a share write fails
after the owned shares file has been replaced, the old file should be restored and the required
`smbd` service path should be restarted so Samba is asked to return to the known-good config. If
that rollback restart fails, the API should surface a controlled operation error with clear detail.

## Acceptance criteria

- [ ] Share publish failure restores the previous SimpleSaferServer-owned shares file.
- [ ] After restoring the previous shares file, rollback attempts to restart `smbd`.
- [ ] Rollback restart failure returns a controlled operation error instead of being hidden behind a generic failure.
- [ ] The existing modal/toast flow surfaces the rollback failure detail from the API problem response.
- [ ] Discovery service restart failures remain best-effort and do not roll back valid share writes.
- [ ] Focused tests cover successful rollback restart and failed rollback restart.
- [ ] `README.md` is not modified.

## Blocked by

None - can start immediately.
