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
- Shared timestamp formatting now supports compact relative labels so dashboard tiles do not grow
  page-local copies of the same elapsed-time logic.
- Follow-up PR feedback tightened remaining API error shapes and JSON parsing, stopped config reads
  from returning raw `rclone.conf`, made fake task runs avoid outbound rclone/DDNS side effects,
  rejected invalid seconds in backup timer input, and rendered dashboard health details without
  assigning API text through `innerHTML`.
- A later review pass also made alert IDs monotonic across retention trimming, propagated alert
  service failures with non-2xx responses, and stopped setup email payloads from logging SMTP
  credentials.
- The follow-up design pass clarified the admin trust model: credential editors should remain useful
  to trusted admins, fake mode should stay close to real provider behavior, and transient status
  should prefer volatile runtime storage to reduce unnecessary persistent writes.

## Follow-up

- Dashboard health intentionally resets to `No check yet` when the web process restarts so the app
  does not add extra persisted health state or SD-card writes.
