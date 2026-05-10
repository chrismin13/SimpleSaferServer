# 0029 App Version Self Update

## Summary

- Add Git-based application version visibility and self-update handling to the System Updates page.
- Surface the recurring application update job through the existing Dashboard scheduled-task table.

## Rules / Constraints

- Preserve Python 3.7 compatibility for Debian 10.
- Keep `main` as the normal install/update path.
- Use the full installer for application updates so services, timers, scripts, dependencies,
  static files, and templates refresh together.
- Check related docs, `index.html`, and `uninstall.sh`.

## Target State

- The System Updates page shows the installed branch or tag, current commit, cached remote check
  time, and whether an update is available.
- Remote Git checks happen only when the admin clicks Refresh.
- Update Now starts the scheduled `App Update` task only when the local checkout is clean, on a
  branch with an upstream, and behind that upstream.

## Phase Checklist

- [x] Phase 1: Add Git status and update service.
- [x] Phase 2: Add systemd task/script and dashboard exposure.
- [x] Phase 3: Add System Updates UI, docs, and tests.

## Work Log

### Phase 1

- Added an application update manager and command adapter around Git and installer commands.
- Status distinguishes branches, tags, detached checkouts, dirty tracked files, behind/ahead, and
  diverged states.

### Phase 2

- Added `app_update.py` and `app_update.sh` helper scripts.
- Added `app_update.service` and `app_update.timer`, scheduled 15 minutes before `Check Mount`.
- Added `App Update` to the existing task service so the dashboard and task detail page can reuse
  current scheduled-task behavior.

### Phase 3

- Added the Application section to System Updates with Refresh and Update Now.
- Updated docs for System Updates and Dashboard.
- Hardened the installer with a shared same-file copy helper so self-updates can rerun it from
  `/opt/SimpleSaferServer` without `cp` failing on files already at their installed path.
- Avoided chmodding same-file script destinations because changing tracked script modes dirties the
  installed Git checkout and blocks the updater.

Docs and uninstall impact:

- `docs/system_updates.md` and `docs/dashboard.md` describe the new behavior.
- `index.html` already links to System Updates and Dashboard docs, so no new index link was needed.
- `uninstall.sh` removes `app_update` service/timer and installed helper scripts.

Verification:

- `.venv/bin/python -m pytest tests/test_app_updates.py tests/test_system_utils.py tests/test_task_service.py tests/test_system_updates.py tests/test_system_updates_routes.py tests/test_uninstall.py` passed.
- `bash check_ci.sh` passed. Pyright reported the existing pytest import warnings in server
  identity tests, with 0 errors.

## Decisions

- Commit SHA is the precise installed version identity.
- Tags and detached checkouts are pinned, visible states; automatic updates require a branch.
- Updates use `git pull --ff-only` and refuse tracked local edits to avoid hidden merges or
  overwritten local changes.

## Follow-Up Backlog

- Add a task-disable mechanism if admins later need to turn off automatic application updates.
