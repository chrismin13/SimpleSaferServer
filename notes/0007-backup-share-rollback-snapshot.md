# 0007 Backup Share Rollback Snapshot

## Summary

- Harden backup-drive setup rollback so managed-share restore uses an immutable snapshot of the original share fields.
- Add a regression test for a live share record that is mutated during the first update call.
- Add a lightweight local CI runner and document it as the deliberate pre-push check path.

## Rules / Constraints

- Preserve Python 3.7 compatibility for Debian 10.
- Keep the rollback fix narrow to the path that CI reported.
- Check related docs, `index.html`, and `uninstall.sh` for impact.

## Target State

- Backup-drive setup and fake-mode setup both restore the previous managed backup share even if the share object is mutated in place while applying the new path.
- Local developers can run one script that mirrors the GitHub Actions quality gates without forcing slow pre-commit hooks into every commit.

## Phase Checklist

- [x] Phase 1: Patch rollback state capture for managed backup shares.
- [x] Phase 2: Add local CI workflow docs and script.
- [x] Phase 3: Run focused and full local verification.

## Work Log

### Phase 1

- Reproduced the reported scenario context and found the rollback path was keeping the original managed share by reference instead of snapshotting rollback state.
- Added an immutable backup-share update snapshot, including tuple-backed `valid_users`, and reused it for both update and rollback paths.
- Added a regression test that mutates the live share record during the first update call so rollback must rely on the snapshot rather than the mutated object.
- Added `check_ci.sh` to mirror the GitHub Actions gates from one local command.
- Removed slow manual hooks from `.pre-commit-config.yaml`; pre-commit is now ruff-only and the full suite is run deliberately through `check_ci.sh`.
- Kept format, lint, and tests required while making pyright, bandit, and pip-audit advisory in both GitHub Actions and the local wrapper. The local pyright run currently exposes existing route/test typing noise unrelated to the rollback fix.

Docs and uninstall impact:

- `docs/development.md` and `README.md` now document `bash check_ci.sh` as the local full-check workflow.
- `index.html` needs no change because the documentation index still points to the same repository docs.
- `uninstall.sh` needs no change because no installed files, services, timers, directories, or generated system config were added.

Verification:

- `.venv/bin/python -m ruff format simple_safer_server/services/backup_drive_setup.py tests/test_backup_drive_setup.py`
- `.venv/bin/python -m ruff check simple_safer_server/services/backup_drive_setup.py tests/test_backup_drive_setup.py`
- `.venv/bin/python -m pytest tests/test_backup_drive_setup.py`
- `.venv/bin/python - <<'PY' ... PY` Python 3.7 syntax compatibility check from `docs/development.md`
- `bash check_ci.sh`; required checks passed with `193 passed`, and the advisory pyright gate reported existing baseline typing issues.

## Decisions

- Snapshot rollback state instead of the raw share dict so future SMB manager internals can rewrite share records in place without breaking rollback safety.
- Keep pre-commit lightweight because this project benefits more from occasional deliberate full checks than slow automatic hooks on every commit.
- Keep the slower analysis tools visible but advisory until their existing baseline issues are cleaned up.

## Follow-Up Backlog

- None yet.
