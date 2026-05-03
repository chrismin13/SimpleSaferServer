# 0021 Schedule Time Normalizer

## Summary

- Consolidate backup schedule time parsing so UI/API writes use strict `HH:MM` while existing
  legacy config values remain readable for systemd timer generation.

## Rules / Constraints

- Preserve Python 3.7 compatibility for Debian 10.
- Preserve existing deployed config compatibility for `H:MM` and `HH:MM:SS` values.
- Keep public write APIs stricter than internal compatibility paths.
- Check related docs, `index.html`, and `uninstall.sh`.

## Target State

- Browser-facing schedule saves store two-digit `HH:MM`.
- Systemd timer generation accepts older persisted shapes and emits `HH:MM:SS`.
- Setup wizard and Cloud Backup share one validation helper instead of carrying separate ad hoc
  regex or timer-generation validation paths.

## Phase Checklist

- [x] Phase 1: Add shared normalizer and route/service integration.
- [x] Phase 2: Add regression tests and documentation updates.

## Work Log

### Phase 1

- Added `services.schedule_time` with strict UI validation, legacy config normalization, and
  systemd expansion helpers.
- Routed setup wizard, Cloud Backup, legacy migration, default config, and systemd timer generation
  through the shared helper.

Docs and uninstall impact:

- Related docs: `docs/setup.md` and `docs/cloud_backup.md`.
- `index.html` already links both related docs.
- No uninstall change is needed because no generated files, services, timers, or directories were
  added.

Verification:

- `.venv/bin/python -m pytest tests/test_schedule_time.py tests/test_setup_wizard.py tests/test_cloud_backup_service.py tests/test_system_utils.py tests/test_migration.py`
- `.venv/bin/python -m ruff check simple_safer_server/services/schedule_time.py simple_safer_server/services/system_utils.py simple_safer_server/services/config_manager.py simple_safer_server/legacy/migration.py simple_safer_server/services/cloud_backup_service.py simple_safer_server/routes/setup_wizard.py tests/test_schedule_time.py tests/test_setup_wizard.py tests/test_cloud_backup_service.py tests/test_system_utils.py`
- `.venv/bin/python -m ruff format --check simple_safer_server/services/schedule_time.py simple_safer_server/services/system_utils.py simple_safer_server/services/config_manager.py simple_safer_server/legacy/migration.py simple_safer_server/services/cloud_backup_service.py simple_safer_server/routes/setup_wizard.py tests/test_schedule_time.py tests/test_setup_wizard.py tests/test_cloud_backup_service.py tests/test_system_utils.py`
- `.venv/bin/pyright`
- `git diff --check`

## Decisions

- Strict `HH:MM` belongs at browser-facing write boundaries because the HTML time input and user
  docs expose that shape.
- Legacy tolerance belongs at migration and systemd consumption boundaries so existing installs
  keep working until their next schedule save normalizes persisted config.

## Follow-Up Backlog

- Consider moving setup wizard schedule saving behind `CloudBackupService.save_schedule` during a
  later route-thinning pass.
