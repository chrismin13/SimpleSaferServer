# 0007 Backup Share Rollback Snapshot

## Summary

- Harden backup-drive setup rollback so managed-share restore uses an immutable snapshot of the original share fields.
- Add a regression test for a live share record that is mutated during the first update call.
- Add lightweight local CI runners and document them as deliberate pre-push check paths.

## Rules / Constraints

- Preserve Python 3.7 compatibility for Debian 10.
- Keep the rollback fix narrow to the path that CI reported.
- Check related docs, `index.html`, and `uninstall.sh` for impact.

## Target State

- Backup-drive setup and fake-mode setup both restore the previous managed backup share even if the share object is mutated in place while applying the new path.
- Local developers can run a fast local check or an exact Python 3.7 Docker reproduction without forcing slow pre-commit hooks into every commit.

## Phase Checklist

- [x] Phase 1: Patch rollback state capture for managed backup shares.
- [x] Phase 2: Add local CI workflow docs and script.
- [x] Phase 3: Run focused and full local verification.

## Work Log

### Phase 1

- Reproduced the reported scenario context and found the rollback path was keeping the original managed share by reference instead of snapshotting rollback state.
- Added an immutable backup-share update snapshot, including tuple-backed `valid_users`, and reused it for both update and rollback paths.
- Added a regression test that mutates the live share record during the first update call so rollback must rely on the snapshot rather than the mutated object.
- Added `check_ci.sh` for strict local checks from one command.
- Added `check_ci_docker.sh` to reproduce the full GitHub Actions gates in `python:3.7-buster`.
- Removed slow manual hooks from `.pre-commit-config.yaml`; pre-commit is now ruff-only and the full suite is run deliberately through `check_ci.sh`.
- Restored pyright, bandit, and pip-audit as strict GitHub Actions gates with no `continue-on-error`. The local wrappers also run them strictly.

Docs and uninstall impact:

- `docs/development.md` and `README.md` now document `bash check_ci.sh` for strict local checks and `bash check_ci_docker.sh` for exact Python 3.7 CI reproduction.
- `index.html` needs no change because the documentation index still points to the same repository docs.
- `uninstall.sh` needs no change because no installed files, services, timers, directories, or generated system config were added.

Verification:

- `.venv/bin/python -m ruff format simple_safer_server/services/backup_drive_setup.py tests/test_backup_drive_setup.py`
- `.venv/bin/python -m ruff check simple_safer_server/services/backup_drive_setup.py tests/test_backup_drive_setup.py`
- `.venv/bin/python -m pytest tests/test_backup_drive_setup.py`
- `.venv/bin/python - <<'PY' ... PY` Python 3.7 syntax compatibility check from `docs/development.md`
- `bash check_ci.sh`; required checks passed with `193 passed`, and the advisory pyright gate reported existing baseline typing issues.
- CI on Python 3.7 failed because `unittest.mock` call objects do not expose keyword arguments the same way as the newer local Python runtime; updated the new assertions to use `call_args[1]` and `call_args_list[-1][1]`.
- Re-ran `.venv/bin/python -m pytest tests/test_backup_drive_setup.py`, `.venv/bin/python -m ruff check tests/test_backup_drive_setup.py`, and the Python 3.7 syntax compatibility check after the assertion compatibility fix.
- Updated `.github/workflows/quality.yml` so the required workflow only runs strict format, lint, and test gates.
- Added `check_ci_docker.sh`; local execution depends on Docker daemon availability.
- Fixed the strict pyright baseline by narrowing setup route helper status types, broadening an update-state dict, and adding explicit test narrowing where values can be optional or union-shaped.
- Re-ran `bash check_ci.sh`; formatting, linting, tests, pyright, bandit, and pip-audit passed locally. Docker CLI is installed, but the daemon socket is not reachable in this workspace, so the Docker reproduction could not start here.

## Decisions

- Snapshot rollback state instead of the raw share dict so future SMB manager internals can rewrite share records in place without breaking rollback safety.
- Keep pre-commit lightweight because this project benefits more from occasional deliberate full checks than slow automatic hooks on every commit.
- Keep pyright, bandit, and pip-audit strict in CI; do not use `continue-on-error` for required gates.

## Follow-Up Backlog

- None yet.
