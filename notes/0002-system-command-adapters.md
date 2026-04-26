# 0002 System Command Adapters

## Summary

- Continue the package refactor by moving subprocess-heavy system behavior behind named adapters.
- Keep public routes, task names, service names, command behavior, and fake-mode behavior unchanged unless a bug is clearly found and documented.

## Rules / Constraints

- Preserve Python 3.7 compatibility for Debian 10.
- Preserve behavior unless a bug is clearly found and documented.
- Keep changes reviewable and avoid unrelated formatting churn.
- Check related docs, `index.html`, and `uninstall.sh`.
- Keep top-level compatibility modules until install, service, and operator docs are intentionally migrated to package entrypoints.

## Target State

- `TaskService` delegates systemd, journalctl, and rclone process behavior to adapters.
- Route modules stay thin; storage, package-manager, SMB, user, and mount helpers move behind service/adapter boundaries in later phases.
- `CommandRunner` remains the shared low-level subprocess boundary for logging, policy, and future fake adapters.

## Phase Checklist

- [x] Phase 1: Move scheduled task systemd/journal/rclone subprocess behavior behind adapters.
- [x] Phase 2a: Move dashboard storage controls behind service/adapter boundaries.
- [x] Phase 2b: Move managed backup-drive unmount helper behind a command adapter.
- [x] Phase 2c: Move backup-drive setup mount/unmount execution behind command adapters.
- [x] Phase 2d: Move backup-drive discovery and fstab system commands behind adapters.
- [x] Phase 3a: Move System Updates support commands behind a command adapter.
- [x] Phase 3b: Move the long-running apt worker process behind a package-manager adapter.
- [x] Phase 4: Move SMB and local user command behavior behind Samba and system-user adapters.
- [ ] Phase 5: Review top-level compatibility entrypoints after install/operator docs are ready to migrate.

## Work Log

### Phase 1

- Added `SystemdAdapter` for task-related `systemctl` and `journalctl` calls.
- Added `RcloneAdapter` for Cloud Backup task `rclone sync` process creation.
- Extended `CommandRunner` with a `popen()` boundary for long-running commands.
- Updated `TaskService` to use injected adapters instead of owning systemd/journal/rclone command shapes directly.
- Kept fake-mode task behavior unchanged, including DDNS script execution through the shared command runner.
- Added focused tests proving real task status, timestamps, logs, start, and stop use the systemd adapter.

Docs and uninstall impact:

- Updated `docs/architecture.md` to name the active system command adapters.
- `index.html` did not need updates because public documentation links did not change.
- `uninstall.sh` did not need updates because this phase added only package source, tests, and notes.

Verification:

- Focused task service tests: passed.
- Focused Ruff check for touched task/adapter files: passed.
- Focused Pyright check for touched task/adapter files: passed.
- Python 3.7 syntax compatibility check: passed.
- Ruff format check: passed.
- Ruff lint: passed.
- Pyright: passed with 0 errors and 0 warnings.
- Bandit: passed with no issues identified.
- Dependency audit: passed with no known vulnerabilities found, retaining the documented Debian 10 pytest advisory ignore.
- Full pytest: 158 passed, with one pre-existing Python 3.14 `datetime.utcnow()` deprecation warning in `user_manager.py`.

### Phase 2a

- Added `StorageCommandAdapter` for dashboard reboot, shutdown, UUID lookup, mount, and service-start commands.
- Added `StorageService` for dashboard restart, shutdown, and mount behavior.
- Updated `routes/storage.py` so the dashboard storage routes delegate command behavior to `StorageService`.
- Added focused storage service tests for fake mount behavior, real mount orchestration, restart/shutdown delegation, missing UUID, and mount command failure responses.
- Left backup-drive setup and unmount helpers for Phase 2b so the larger mount workflow stays reviewable.

Docs and uninstall impact:

- `docs/architecture.md` already describes system command adapters and does not need a user-facing link change for this internal boundary.
- `index.html` did not need updates because public documentation links did not change.
- `uninstall.sh` did not need updates because this phase added only package source and tests.

Verification:

- Focused storage service and app-factory route tests: passed.
- Focused Ruff check for touched storage files: passed.
- Focused Pyright check for touched storage files: passed.
- Python 3.7 syntax compatibility check: passed.
- Ruff format check: passed.
- Ruff lint: passed.
- Pyright: passed with 0 errors and 0 warnings.
- Bandit: passed with no issues identified.
- Dependency audit: passed with no known vulnerabilities found, retaining the documented Debian 10 pytest advisory ignore.
- Full pytest: 163 passed, with one pre-existing Python 3.14 `datetime.utcnow()` deprecation warning in `user_manager.py`.

### Phase 2b

- Added `BackupDriveCommandAdapter` for managed backup-drive unmount commands.
- Updated `backup_drive_unmount.py` to use the adapter for SMB close-share, service stop/start, unmount, UUID lookup, and disk power-down commands.
- Kept `unmount_managed_backup_drive()` as the compatibility entrypoint and added an optional adapter injection point for focused tests.
- Updated backup-drive unmount tests to assert behavior through a fake command adapter instead of patching subprocess directly.
- Left `backup_drive_setup.py` for Phase 2c because it has a larger formatting, fstab, mount, rollback, and drive-list workflow.

Docs and uninstall impact:

- `docs/architecture.md` already describes backup-drive command adapter migration as internal architecture work.
- `index.html` did not need updates because public documentation links did not change.
- `uninstall.sh` did not need updates because this phase added only package source and tests.

Verification:

- Focused backup-drive unmount tests: passed.
- Focused Ruff check for touched unmount files: passed.
- Focused Pyright check for touched unmount files: passed.
- Python 3.7 syntax compatibility check: passed.
- Ruff format check: passed.
- Ruff lint: passed.
- Pyright: passed with 0 errors and 0 warnings.
- Bandit: passed with no issues identified.
- Dependency audit: passed with no known vulnerabilities found, retaining the documented Debian 10 pytest advisory ignore.
- Full pytest: 163 passed, with one pre-existing Python 3.14 `datetime.utcnow()` deprecation warning in `user_manager.py`.

### Phase 2c

- Extended `BackupDriveCommandAdapter` with setup-oriented partition unmount, NTFS mount, and cleanup unmount methods.
- Updated `backup_drive_setup.py` so disk-partition unmount, selected-partition unmount, NTFS mount, and rollback cleanup unmount use the adapter.
- Kept the top-level setup module and helper names intact for compatibility.
- Updated setup tests to inject a fake command adapter for the touched mount/unmount behavior.
- Left drive discovery, filesystem probing, UUID lookup, and systemd daemon reload commands for Phase 2d.

Docs and uninstall impact:

- `docs/architecture.md` already records that backup-drive setup command migration is still in progress.
- `index.html` did not need updates because public documentation links did not change.
- `uninstall.sh` did not need updates because this phase added only source and tests.

Verification:

- Focused backup-drive setup/unmount tests: passed.
- Focused Ruff check for touched backup-drive files: passed.
- Focused Pyright check for touched backup-drive files: passed.
- Python 3.7 syntax compatibility check: passed.
- Ruff format check: passed.
- Ruff lint: passed.
- Pyright: passed with 0 errors and 0 warnings.
- Bandit: passed with no issues identified.
- Dependency audit: passed with no known vulnerabilities found, retaining the documented Debian 10 pytest advisory ignore.
- Full pytest: 163 passed, with one pre-existing Python 3.14 `datetime.utcnow()` deprecation warning in `user_manager.py`.

### Phase 2d

- Extended `BackupDriveCommandAdapter` for backup-drive discovery, filesystem probing, UUID lookup, and systemd daemon reload.
- Updated `backup_drive_setup.py` so it no longer imports or calls `subprocess` directly.
- Preserved the existing top-level compatibility module and helper function names.
- Kept fake-mode behavior unchanged.

Docs and uninstall impact:

- `docs/architecture.md` already describes the backup-drive adapter boundary.
- `index.html` did not need updates because public documentation links did not change.
- `uninstall.sh` did not need updates because this phase changed only source and tests.

Verification:

- Focused backup-drive setup tests: passed.
- Focused Ruff check for touched setup files: passed.
- Focused Pyright check for touched setup files: passed.
- Python 3.7 syntax compatibility check: passed.
- Ruff format check: passed.
- Ruff lint: passed.
- Pyright: passed with 0 errors and 0 warnings.
- Bandit: passed with no issues identified.
- Dependency audit: passed with no known vulnerabilities found, retaining the documented Debian 10 pytest advisory ignore.
- Full pytest: 163 passed, with one pre-existing Python 3.14 `datetime.utcnow()` deprecation warning in `user_manager.py`.

### Phase 3a

- Added `SystemUpdatesCommandAdapter` for package-manager support commands outside the long-running apt worker.
- Moved stale-lock removal, fuser lock checks, APT periodic config writes, Livepatch status checks, and Ubuntu Pro Livepatch setup commands behind the adapter.
- Kept the long-running apt update/upgrade worker process in `SystemUpdatesManager` for Phase 3b.
- Updated System Updates tests to inject a fake command adapter for config-write and Livepatch setup behavior.

Docs and uninstall impact:

- `docs/architecture.md` already describes package-manager adapter migration as internal architecture work.
- `index.html` did not need updates because public documentation links did not change.
- `uninstall.sh` did not need updates because this phase added only package source and tests.

Verification:

- Focused System Updates tests: passed.
- Focused Ruff check for touched System Updates files: passed.
- Focused Pyright check for touched System Updates files: passed.
- Python 3.7 syntax compatibility check: passed.
- Ruff format check: passed.
- Ruff lint: passed.
- Pyright: passed with 0 errors and 0 warnings.
- Bandit: passed with no issues identified.
- Dependency audit: passed with no known vulnerabilities found, retaining the documented Debian 10 pytest advisory ignore.
- Full pytest: 163 passed, with one pre-existing Python 3.14 `datetime.utcnow()` deprecation warning in `user_manager.py`.

### Phase 3b

- Moved the long-running apt update/upgrade worker process creation into `SystemUpdatesCommandAdapter`.
- Moved apt worker process-group termination into the adapter.
- Updated System Updates routes to catch the shared `CalledProcessError` export instead of importing `subprocess`.
- `system_updates.py` and `simple_safer_server/routes/system_updates.py` no longer import or call `subprocess` directly.

Docs and uninstall impact:

- Updated `docs/architecture.md` to describe the completed System Updates adapter boundary.
- `index.html` did not need updates because public documentation links did not change.
- `uninstall.sh` did not need updates because this phase changed only source and tests.

Verification:

- Focused System Updates tests: passed.
- Focused Ruff check for touched System Updates files: passed.
- Focused Pyright check for touched System Updates files: passed.

### Phase 4

- Added `SmbCommandAdapter` for Samba config backup, validation, service restart, and service status commands.
- Updated `SMBManager` to use the SMB adapter while preserving fake-mode service state behavior.
- Added `UserCommandAdapter` for local account checks/creation and Samba user/password commands.
- Updated `UserManager` to use the user adapter for `id`, `useradd`, `pdbedit`, and `smbpasswd` command behavior.
- `smb_manager.py` and `user_manager.py` no longer import or call `subprocess` directly.

Docs and uninstall impact:

- Updated `docs/architecture.md` to describe the SMB and user-management adapter boundaries.
- `index.html` did not need updates because public documentation links did not change.
- `uninstall.sh` did not need updates because this phase added only package source and tests.

Verification:

- Focused SMB manager, auth decorator, and app-factory route tests: passed.
- Focused Ruff check for touched SMB/user files: passed.
- Focused Pyright check for touched SMB/user files: passed.
- Python 3.7 syntax compatibility check: passed.
- Ruff format check: passed.
- Ruff lint: passed.
- Pyright: passed with 0 errors and 0 warnings.
- Bandit: passed with no issues identified.
- Dependency audit: passed with no known vulnerabilities found, retaining the documented Debian 10 pytest advisory ignore.
- Full pytest: 163 passed, with one pre-existing Python 3.14 `datetime.utcnow()` deprecation warning in `user_manager.py`.

## Decisions

- `CommandRunner.popen()` mirrors the small subset of `subprocess.Popen` currently needed so adapters can move command construction out of services without a broad process-management rewrite.
- `SystemdAdapter` returns raw systemd property output because `TaskService` already owns the display mapping and fallback strings used by templates.
- Top-level compatibility modules remain in place until a later phase updates install, service, and operator entrypoints deliberately.

## Follow-Up Backlog

- Review remaining subprocess surfaces in setup wizard, drive health, legacy migration, system utils, and standalone helper scripts.
- Move `backup_drive_setup.py` and `backup_drive_unmount.py` command execution behind mount/system adapters while keeping compatibility imports stable.
- Move `SystemUpdatesManager` apt/dpkg command behavior behind a package-manager adapter.
- Move SMB and local user commands behind Samba and system-user adapters.
