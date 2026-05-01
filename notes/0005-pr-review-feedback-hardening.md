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
- Setup wizard JSON POST routes now use a setup-specific JSON object parser and return `400` for
  missing, invalid, or non-object JSON bodies.
- Dashboard drive health now reads a RAM-only last-known summary. The Dashboard refresh button is
  the explicit path that runs live SMART/HDSentinel probes and updates that in-process summary.
- Generated timers now keep the cloud backup at the configured time, run the mount check 4 minutes
  before backup, and run drive health 2 minutes before backup so randomized delay has less chance
  to overlap mount and health work.

## Follow-up

- Dashboard health intentionally resets to `No check yet` when the web process restarts so the app
  does not add extra persisted health state or SD-card writes.
