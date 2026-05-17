# Samba Pre-Submit Cleanup PRD

## Problem Statement

The Samba discovery/config redesign and effective-config hardening work is functionally complete and
tests pass, but a pre-merge review found four issues that should be fixed before the changes are
committed:

1. The share-user helper (`get_share_users`, `update_share_users`) depends on Effective Samba Config
   inspection even though it only operates on SimpleSaferServer-Managed Shares. A broken admin-owned
   Samba include can block reading or updating users for a share SimpleSaferServer already owns.

2. The drive health documentation still tells operators to check `/etc/samba/smb.conf` as the share
   config, when managed shares now live in `/etc/samba/simple_safer_server_shares.conf`.

3. The old inline managed-share machinery (marker constants, `_commit_smb_conf`, `_write_smb_conf`,
   `_validate_smb_conf_candidate`, `_restore_smb_conf_backup`, `_create_backup`, and the marker
   check inside `_parse_smb_conf`) is dead code that contradicts the new file-path ownership model
   and could mislead future maintainers.

4. The Network File Sharing page uses a binary green/red badge for discovery services (`nmbd`,
   `wsdd2`). When `wsdd2` is not installed, the API returns `unavailable`, which shows a red badge
   as if something is broken. Discovery services are best-effort and deserve a three-tier badge.

## Solution

Fix the four issues in place without changing the overall Samba redesign architecture.

- Make `_get_managed_share_or_raise()` check the SimpleSaferServer-owned shares file first. Only
  inspect unmanaged shares afterward, and only to produce the "not managed by SimpleSaferServer"
  error message.
- Update `docs/drive_health.md` to reference the SSS shares file and the Network File Sharing page.
- Remove the dead inline managed-share code from SMBManager.
- Use three badge tiers for discovery services: green for `active`, yellow for `inactive`, grey for
  `unavailable`. Keep smbd binary (green/red) since it is the hard requirement.

## User Stories

1. As an administrator, I want to read share users for an existing SimpleSaferServer-Managed Share even when an unrelated Samba include is broken, so that Effective Config problems do not block routine share management.
2. As an administrator, I want to update share users for an existing SimpleSaferServer-Managed Share without depending on Effective Config inspection, so that ownership-based edits stay resilient.
3. As an administrator, I want the drive health docs to point me to the correct file for managed shares, so that manual recovery guidance matches the actual system layout.
4. As an administrator, I want the `wsdd2` badge to show grey when the package is not installed, so that I can distinguish "not available on this system" from "installed but broken."
5. As an administrator, I want the `nmbd` badge to show yellow when inactive, so that I can see it is worth noticing without being alarmed by a red badge for a best-effort service.
6. As an administrator, I want the `smbd` badge to stay red when inactive, so that the hard file-serving requirement is visually distinct from optional discovery.
7. As a future maintainer, I want the old marker-based managed-share code removed, so that the codebase does not look like it supports two ownership models.
8. As a future maintainer, I want `_get_managed_share_or_raise()` to clearly separate ownership proof from conflict detection, so that the dependency boundary is obvious in code.
9. As a future maintainer, I want no dead `_commit_smb_conf` or `_write_smb_conf` methods, so that a future edit cannot accidentally reintroduce direct smb.conf share writes.
10. As a future maintainer, I want the `MANAGED_SHARE_BEGIN_PREFIX` constant removed, so that grep results do not suggest legacy marker support is still active.

## Implementation Decisions

- `_get_managed_share_or_raise()` should call `_load_managed_shares_file()` first. If the share is found there, return it immediately without touching Effective Config inspection.
- After the managed lookup fails, optionally inspect unmanaged shares to produce the "not managed" error. If that inspection also fails, fall back to a generic "share not found" error.
- The following dead methods and constants should be removed from SMBManager: `MANAGED_SHARE_BEGIN_PREFIX`, `MANAGED_SHARE_END_PREFIX`, `_create_backup()`, `_write_smb_conf()`, `_validate_smb_conf_candidate()`, `_restore_smb_conf_backup()`, `_commit_smb_conf()`.
- The `self.backup_dir` attribute and its `mkdir` in `__init__` should be removed since nothing writes to it after the dead methods are gone. The `samba_backup_dir` runtime field stays untouched (separate cleanup).
- The `MANAGED_SHARE_BEGIN_PREFIX` break check inside `_parse_smb_conf()` should be removed. That method is still used by effective-config inspection but should parse testparm output without legacy marker awareness.
- `docs/drive_health.md` line 178 should reference the Network File Sharing page and the SSS shares file. Line 186 should list `/etc/samba/simple_safer_server_shares.conf` as the managed share config location.
- Discovery service badge logic in the Network File Sharing template should use: `active` → `badge-success`, `inactive` → `badge-warning`, `unavailable` → `badge-neutral`.
- The `smbd` badge stays binary: `active` → `badge-success`, anything else → `badge-danger`.
- The same three-tier logic applies to both `nmbd` and `wsdd2` badges for consistency, even though `nmbd` is unlikely to return `unavailable` in practice.

## Testing Decisions

Good tests should verify external behavior and safety boundaries. The important new behavior is that
managed-share user reads succeed independently of Effective Config inspection, and that dead code
removal does not regress existing share management paths.

Modules and behaviors to test:

- SMBManager:
  - `get_share_users()` succeeds for an existing SimpleSaferServer-Managed Share when Effective Config inspection would fail.
  - `update_share_users()` succeeds for an existing SimpleSaferServer-Managed Share when Effective Config inspection would fail.
  - `get_share_users()` raises a clear error for an unmanaged share name (when inspection succeeds).
  - `get_share_users()` raises a clear error for a share that does not exist anywhere.
  - All existing SMBManager tests remain green after dead code removal.
- Network File Sharing template (if existing pattern supports it):
  - `wsdd2` status `unavailable` renders a neutral badge class.
  - `wsdd2` status `inactive` renders a warning badge class.
  - `nmbd` status `inactive` renders a warning badge class.
  - `smbd` status `inactive` renders a danger badge class.

Prior art:

- Existing `tests/test_smb_manager.py` covers share user helpers, unmanaged conflict rejection, and
  service status behavior.
- Existing `tests/test_app_factory_routes.py` covers Network File Sharing page rendering and API
  response structure.

## Out of Scope

- Removing `samba_backup_dir` from the runtime dataclass or its initialization.
- Changing the Samba ownership model or layout helper behavior.
- Adding new features to the Network File Sharing page.
- Modifying the installer or uninstaller scripts.
- Editing `README.md`.

## Further Notes

This PRD is a follow-up to the pre-merge code review of the Samba discovery/config redesign and
effective-config hardening work. All four findings were discussed and agreed before this PRD was
written. The existing 137 tests pass on the current uncommitted state; this work should keep them
green while adding targeted coverage for the `_get_managed_share_or_raise` fix.
