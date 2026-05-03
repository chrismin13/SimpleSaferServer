# 0020 File Persistence Pattern

## Summary

- Standardize app-owned file writes so small state/config files are published with atomic replace,
  while long append-heavy logs keep append semantics.

## Rules / Constraints

- Preserve Python 3.7 compatibility for Debian 10.
- Preserve behavior unless a bug is clearly found and documented.
- Keep changes reviewable and avoid unrelated formatting churn.
- Check related docs, `index.html`, and `uninstall.sh`.

## Target State

- Shared persistence helpers own temp-file, fsync, replace, sidecar lock, and cleanup mechanics.
- Alerts use one domain store from both the web app and standalone script.
- System-file workflows keep validation, backup, restart, and rollback logic close to their domains.

## Phase Checklist

- [x] Phase 1: Add shared persistence helpers and tests.
- [x] Phase 2: Migrate alerts to a shared store.
- [x] Phase 3: Migrate straightforward app-owned JSON/config writers.
- [x] Phase 4: Document the policy.

## Work Log

### Phase 1

- Added `file_persistence` helpers for atomic text/JSON writes, sidecar locks, and locked JSON
  read/modify/write transactions.
- Added `AlertStore` so web and script alert writers share ID, retention, lock, and replace
  behavior.
- Kept alert initialization under the same sidecar lock so first-run concurrent scripts cannot
  overwrite another process's freshly appended alert.
- Migrated straightforward app-owned writers for alerts, secrets, users, fake state, DDNS status,
  drive-health state, system-update state, generated systemd units, rclone/msmtp config, and apt
  periodic config staging.
- Left append-heavy logs and domain-validated system-file flows outside the generic JSON/state
  abstraction.

Docs and uninstall impact:

- Updated `docs/development.md` with the persistence policy.
- Checked `index.html`; no direct persistence documentation links needed.
- Checked `uninstall.sh`; existing config/data cleanup covers sidecar locks and temp files, and
  installed scripts are already listed.

Verification:

- `.venv/bin/python -m ruff check ...` passed for changed code/tests.
- `.venv/bin/python -m pytest tests/test_file_persistence.py tests/test_log_alert.py tests/test_config_manager.py tests/test_user_manager.py tests/test_runtime.py tests/test_ddns_update.py tests/test_drive_health.py tests/test_system_updates.py tests/test_system_utils.py tests/test_runtime_command_adapters.py` passed.
- `bash check_ci.sh` passed with 250 tests.
- Python 3.7 syntax parse passed for changed Python files.

## Decisions

- Use atomic copy-on-write replacement for small state/config files.
- Do not rewrite append-heavy logs for every appended line.
- Use sidecar lock files for cross-process read/modify/write state; locking the replaced target file
  can leave processes locking different inodes after `os.replace`.

## Follow-Up Backlog

- Consider moving remaining system-file writer mechanics to the shared helpers when doing focused
  Samba, fstab, apt, or systemd hardening.
