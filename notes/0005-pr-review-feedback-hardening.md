# PR Review Feedback Hardening

## Context

PR #43 review comments called out several places where route handlers could return misleading
success responses, expose raw exception text, or leave credential and user-account state out of
sync with system services.

## Changes

- User creation now defaults to non-admin, with setup and migration flows passing `is_admin=True`
  where they intentionally create the initial administrator.
- Admin password resets use `UserManager.set_password()` so password policy checks and Samba
  synchronization stay in one service path.
  rclone config even when reusing a stored password.
- Task, alert, SMB, storage, and system-updates routes now prefer client-safe API errors and more
  accurate non-2xx statuses for expected failures.
- Command execution gained timeout plumbing for drive-health probes, and backup-drive NTFS mounts
  use the current process UID/GID instead of hard-coded `1000`.

## Follow-up

- The setup wizard still has several older JSON parsing paths that would benefit from a dedicated
  pass using the shared API helpers.
- Dashboard drive health remains a degraded status unless a future pass wires real SMART summary
  data into the dashboard render context.
