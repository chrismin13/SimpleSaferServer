# CodeRabbit Review Hardening

## Summary

Verified the current CodeRabbit review findings before changing code. The round focuses on
maintainability and operator safety: documenting the pip cap, keeping setup configuration out of
routine logs, making progress updates accessible, preserving command-adapter injection for NTFS
verification, and preventing concurrent secret writes from losing updates.

## Decisions

- Use a lock file plus atomic replace for `.secrets` updates so concurrent admin requests cannot
  clobber different secret keys.
- Keep setup logs useful without dumping configuration values; missing-field diagnostics remain
  explicit because they contain schema names rather than managed secrets.
- Thread the backup-drive command adapter through the `fuseblk` verification path so tests and fake
  command boundaries exercise the same behavior as production code.

## Checklist

- [x] Address verified CodeRabbit findings.
- [x] Run focused tests and local quality checks for touched areas.
- [x] Rerun `coderabbit review` after the hourly review cap clears.
- [x] Commit the review/fix round without pushing.

## Verification

- `.venv/bin/python -m ruff format simple_safer_server/services/config_manager.py simple_safer_server/services/backup_drive_setup.py simple_safer_server/routes/setup_wizard.py tests/test_backup_drive_setup.py tests/test_config_manager.py`
- `.venv/bin/python -m ruff check simple_safer_server/services/config_manager.py simple_safer_server/services/backup_drive_setup.py simple_safer_server/routes/setup_wizard.py tests/test_backup_drive_setup.py tests/test_config_manager.py`
- `.venv/bin/python -m pytest tests/test_backup_drive_setup.py tests/test_config_manager.py tests/test_setup_wizard.py tests/test_system_updates.py`
- `coderabbit review` was attempted after the fix round, but CodeRabbit rejected the run because
  the organization hit its hourly review cap.
- A second `coderabbit review` attempt at 2026-05-02 14:04 UTC was rejected for the same hourly
  review cap, so there is no fresh review output to address yet.
- A third `coderabbit review` attempt at 2026-05-02 14:04 UTC was also rejected for the same hourly
  review cap.

## Additional Review Batch

Verified the follow-up inline/duplicate/nitpick comment batch against the current tree. All 16
findings were relevant: some were behavior fixes, while the rest were comments or documentation
that explain compatibility and operational contracts future maintainers could easily miss.

### Decisions

- Remove the duplicate `/run_task/<task_name>` route because no template or static code references
  it, and the explicit `/task/<task_name>/start` route already owns task starts.
- Keep dashboard storage state split between `is_mounted` and `disk_available` so mount controls
  follow the OS mount state while storage usage follows disk usage availability.
- Use microsecond `checked_at` values plus an internal publish sequence for drive-health summaries
  so later same-timestamp publishes win without exposing the sequence in API responses.

### Verification

- `.venv/bin/python -m ruff format --check simple_safer_server/legacy/migration.py simple_safer_server/routes/tasks.py simple_safer_server/routes/storage.py simple_safer_server/services/cloud_backup_service.py simple_safer_server/services/drive_health.py simple_safer_server/adapters/backup_drive_commands.py simple_safer_server/adapters/storage_commands.py tests/test_backup_drive_command_adapter.py tests/test_smb_command_adapter.py tests/test_cloud_backup_service.py tests/test_drive_health.py tests/test_drive_health_summary.py tests/test_migration.py`
- `.venv/bin/python -m ruff check simple_safer_server/legacy/migration.py simple_safer_server/routes/tasks.py simple_safer_server/routes/storage.py simple_safer_server/services/cloud_backup_service.py simple_safer_server/services/drive_health.py simple_safer_server/adapters/backup_drive_commands.py simple_safer_server/adapters/storage_commands.py tests/test_backup_drive_command_adapter.py tests/test_smb_command_adapter.py tests/test_cloud_backup_service.py tests/test_drive_health.py tests/test_drive_health_summary.py tests/test_migration.py`
- `.venv/bin/python -m pytest tests/test_backup_drive_command_adapter.py tests/test_smb_command_adapter.py tests/test_cloud_backup_service.py tests/test_drive_health.py tests/test_drive_health_summary.py tests/test_migration.py tests/test_runtime_command_adapters.py`
- `.venv/bin/python - <<'PY' ... yaml.safe_load(Path('.github/workflows/python-ci.yml').read_text()) ... PY`

## CodeRabbit Rerun After Additional Batch

`coderabbit review` completed and returned 5 relevant findings. The follow-up fixes strengthen
test assertions, create secret files with private permissions at inode creation time, make the
partition-parent fallback actually strip suffixes, use timezone-aware user creation timestamps, and
avoid persisting users when Samba sync fails.

### Verification

- `.venv/bin/python -m ruff format --check simple_safer_server/services/config_manager.py simple_safer_server/services/system_utils.py simple_safer_server/services/user_manager.py tests/test_config_manager.py tests/test_system_utils.py tests/test_user_manager.py tests/test_drive_health.py`
- `.venv/bin/python -m ruff check simple_safer_server/services/config_manager.py simple_safer_server/services/system_utils.py simple_safer_server/services/user_manager.py tests/test_config_manager.py tests/test_system_utils.py tests/test_user_manager.py tests/test_drive_health.py`
- `.venv/bin/python -m pytest tests/test_config_manager.py tests/test_system_utils.py tests/test_user_manager.py tests/test_drive_health.py`
