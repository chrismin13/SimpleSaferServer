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
- [ ] Rerun `coderabbit review` after the hourly review cap clears.
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
