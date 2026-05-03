# 0018 Review Follow-Up Hardening

## Context

A code review against `main` found a dashboard storage rendering regression and then expanded into
root-run helper and first-run setup hardening. The local branch still has a `README.md` change from
the existing changeset, but repository instructions say not to edit that file in this workflow.

## Changes

- Preserved the initial dashboard disk usage result instead of clearing it after `psutil.disk_usage`.
- Added a dashboard render regression assertion so mounted storage is visible before browser polling.
- Removed the installer's unnecessary `sudo` dependency while preserving the current behavior of
  continuing when the upstream rclone installer fails.
- Updated System Updates documentation to describe the actual root-run commands without `sudo`.
- Changed generated script config serialization to `ConfigParser` so multiline setup values cannot
  create accidental extra root-script config keys or sections.
- Validated cloud-backup bandwidth limits on the server and passed the shell helper's rclone
  bandwidth option as an array argument.
- Quoted root-run helper script email arguments and matched USB IDs with fixed-string grep.
- Aligned the standalone alert logger with the main alert store's monotonic ID behavior and added
  a test-only config-directory override.
- Restored `backup.from_address` in the generated script config so scheduled shell helpers receive
  the sender address saved by setup.

## Verification

- Focused tests passed for dashboard/storage, setup/system utils, cloud backup, task service,
  install preflight, install dev, and uninstall paths.
- `bash check_ci.sh` passed after the dashboard, installer, setup/config, cloud-backup, and helper
  hardening changes.

## Follow-Up

- Resolve the branch's `README.md` change manually or with explicit user direction, because the
  repo-level instruction says assistants must not edit `README.md`.
