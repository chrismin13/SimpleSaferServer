# App Update Task Log Visibility

## Summary

- Make web-started application updates send administrators to the existing `App Update` task log.
- Stream updater command output into systemd's journal so the task page shows the same useful
  installer progress as an SSH session.

## Rules / Constraints

- Preserve Python 3.7 compatibility for Debian 10.
- Keep the task page as the single app-update log surface instead of adding another inline log UI.
- Check related docs, `index.html`, and `uninstall.sh`.

## Target State

- **Update Now** starts `app_update.service` and navigates to `/task/App Update`.
- `App Update` journal output includes the Git and `install.sh` output from successful runs.
- Task-log polling keeps retrying through the brief web-service restart during installation.

## Phase Checklist

- [x] Phase 1: Stream app-update command output and start cleanup updates through the task.
- [x] Phase 2: Redirect UI to the task log and improve reconnect behavior.
- [x] Phase 3: Update docs and run focused verification.

## Work Log

### Phase 1

- Added journal-streaming Git and installer command methods for app-update runs.
- Added a volatile cleanup-update request file under `/run/SimpleSaferServer` so the next
  `app_update.service` run can perform cleanup mode without doing installer work in the web
  request.
- Updated `scripts/app_update.py` to consume the queued mode and run normal or cleanup updates with
  stdout/stderr inherited by systemd.

### Phase 2

- Updated System Updates app-update actions to return the `App Update` task URL and navigate there
  after the task starts.
- Updated task-log polling to keep retrying after temporary fetch failures and show a reconnecting
  status near the auto-refresh control.

Docs and uninstall impact:

- `docs/system_updates.md` and `docs/dashboard.md` now describe the task-log handoff and reconnect
  behavior.
- `index.html` already links to the related System Updates and Dashboard docs.
- `uninstall.sh` needs no change because the only new state is volatile runtime state under
  `/run/SimpleSaferServer`.

Verification:

- `.venv/bin/python -m pytest tests/test_app_updates.py tests/test_system_updates_routes.py tests/test_task_service.py` passed.
- `.venv/bin/python -m ruff check simple_safer_server/adapters/app_update_commands.py simple_safer_server/services/app_updates.py simple_safer_server/routes/system_updates.py scripts/app_update.py tests/test_app_updates.py tests/test_system_updates_routes.py` passed.
- `.venv/bin/python -m py_compile simple_safer_server/services/app_updates.py simple_safer_server/adapters/app_update_commands.py simple_safer_server/routes/system_updates.py scripts/app_update.py` passed.
- `node --check static/js/system_updates.js && node --check static/js/scripts.js` passed.
- `git diff --check` passed.

## Decisions

- Use systemd journal output as the source of truth because it survives the web worker restart
  better than an in-page request.

## Follow-Up Backlog

- None yet.
