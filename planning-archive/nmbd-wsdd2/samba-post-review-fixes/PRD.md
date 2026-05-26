# Samba Post-Review Fixes PRD

## Problem Statement

A code review of the uncommitted Samba discovery/config redesign, effective-config hardening, and
pre-submit cleanup work found three remaining issues that should be fixed before the changes are
committed:

1. **Uninstall never restarts Samba** after removing SimpleSaferServer include blocks from
   `smb.conf` and deleting the owned include files. The running `smbd` keeps stale in-memory config
   until the next reboot or manual restart. Active file transfers will be interrupted by the
   restart, so the uninstall confirmation prompt must warn about this upfront.

2. **Uninstall deletes owned files even when marker stripping fails**, leaving `smb.conf` with
   `include` directives pointing to nonexistent files. Samba will fail to start on next restart.
   The current behavior is acceptable (clean up SSS artifacts regardless), but the admin needs a
   loud, actionable warning with exact manual recovery steps.

3. **Dead code remains**: `samba_backup_dir` in the runtime dataclass, `copy_config` on
   `SmbCommandAdapter`, and the legacy `/etc/samba/backups` directory created by older installs are
   all unused after the redesign removed the backup-before-write pattern from SMBManager.

## Solution

Fix the three issues in the uninstall script, runtime, adapter, and documentation without changing
the Samba ownership model or layout helper behavior.

- Add a best-effort `smbd` restart after successful Samba cleanup in the uninstall script.
- Add a Samba disconnect warning to the top-level uninstall confirmation prompt.
- Add a loud warning with manual recovery steps when marker stripping fails but owned files are
  deleted.
- Remove `samba_backup_dir` from the runtime dataclass, its resolution, and its `mkdir` call.
- Remove `copy_config` from `SmbCommandAdapter` and its test.
- Add `rmdir /etc/samba/backups 2>/dev/null || true` to the uninstall script to clean up the empty
  legacy directory without removing any backup files an admin might still want.
- Update `docs/uninstall.md`, `index.html`, and the uninstall script's final summary to reflect the
  restart behavior and Samba disconnect warning.

## User Stories

1. As an administrator, I want Samba to be restarted after uninstall removes its include wiring, so that the running service matches the on-disk config immediately.
2. As an administrator, I want the uninstall confirmation to warn me that active Samba file transfers will be interrupted, so that I can finish transfers or warn users before proceeding.
3. As an administrator, I want a clear error message with exact recovery steps when the uninstall cannot strip SimpleSaferServer markers from `smb.conf`, so that I know how to fix Samba manually.
4. As an administrator, I want the legacy empty `/etc/samba/backups` directory cleaned up during uninstall, so that no SimpleSaferServer artifacts linger after removal.
5. As an administrator, I want old backup files in `/etc/samba/backups` preserved during uninstall, so that I can use them for manual recovery if something went wrong.
6. As a future maintainer, I want `samba_backup_dir` removed from the runtime, so that the codebase does not suggest a backup-before-write pattern that no longer exists.
7. As a future maintainer, I want `copy_config` removed from the command adapter, so that dead adapter methods do not mislead about the system's actual capabilities.

## Implementation Decisions

- The uninstall script's `cleanup_managed_smb_shares` function should call
  `systemctl restart smbd 2>/dev/null || echo "WARNING: ..."` after successfully rewriting
  `smb.conf` and deleting owned files. Restart failure is best-effort — warn and continue.
- Discovery services (`nmbd`, `wsdd2`) are NOT restarted during uninstall. They are shared system
  services and the uninstaller's policy is to leave them running.
- The top-level uninstall confirmation prompt should include:
  "Active Samba file transfers will be interrupted."
- When the Python marker-stripping script fails (malformed markers), the uninstall should print a
  warning like: "WARNING: /etc/samba/smb.conf still contains include lines referencing the deleted
  files. Remove lines referencing simple_safer_server_globals.conf and
  simple_safer_server_shares.conf from /etc/samba/smb.conf, then run: systemctl restart smbd"
- `samba_backup_dir` should be removed from: the runtime dataclass field, `resolve_*` helpers,
  `get_runtime()` construction, `FakeState` initialization, and the `mkdir` call.
- `copy_config` should be removed from `SmbCommandAdapter` and `test_smb_command_adapter.py`.
- Test fixtures that set `samba_backup_dir` on fake runtimes should drop that field.
- Add `rmdir /etc/samba/backups 2>/dev/null || true` to the uninstall script. Only removes if
  empty; non-empty directories with old backup files are left untouched silently.

## Testing Decisions

Good tests should verify the observable behavior of the uninstall script's Samba cleanup path and
confirm dead code is actually removed.

Modules and behaviors to test:

- Uninstall script (`tests/test_uninstall.py`):
  - Successful cleanup restarts `smbd` (best-effort).
  - Restart failure after cleanup warns but does not fail the function.
  - Malformed markers path prints the manual recovery warning with file names and `systemctl restart smbd`.
  - Legacy backup directory is removed when empty, left alone when non-empty.
  - Top-level confirmation text includes the Samba disconnect warning.
- Runtime and adapter:
  - `samba_backup_dir` attribute no longer exists on the runtime.
  - `copy_config` method no longer exists on `SmbCommandAdapter`.
- Existing tests must remain green after removing `samba_backup_dir` from fixtures.

Prior art:

- `tests/test_uninstall.py` already tests `cleanup_managed_smb_shares` with fake `systemctl` and
  temp directories.
- `tests/test_smb_manager.py` and `tests/test_samba_layout.py` use `SimpleNamespace` runtimes that
  will need `samba_backup_dir` removed.
- `tests/test_smb_command_adapter.py` has the `copy_config` test to remove.

## Out of Scope

- Changing the Samba ownership model or layout helper behavior.
- Modifying the installer script's service setup logic.
- Adding new features to the Network File Sharing page.
- Editing `README.md`.
- Removing or modifying old backup files in `/etc/samba/backups`.

## Further Notes

This PRD is a follow-up to the code review of the combined Samba redesign changeset. The decisions
were reached through a grilling session that weighed Samba runtime safety against clean artifact
removal. The key trade-off: we accept that malformed-marker uninstalls leave `smb.conf` in a broken
state (it was likely already broken), but we give the admin exact steps to recover instead of
silently breaking Samba.
