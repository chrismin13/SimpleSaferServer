# Remove dead inline managed-share machinery

## What to build

Remove the old marker-based managed-share code from SMBManager that is no longer called by any
active path. The new file-path ownership model replaced this machinery, and leaving it in place
makes the codebase look like two ownership models are supported.

Remove:
- `MANAGED_SHARE_BEGIN_PREFIX` and `MANAGED_SHARE_END_PREFIX` constants
- `_create_backup()` method
- `_write_smb_conf()` method
- `_validate_smb_conf_candidate()` method
- `_restore_smb_conf_backup()` method
- `_commit_smb_conf()` method
- `self.backup_dir` attribute and its `mkdir` in `__init__`
- The `MANAGED_SHARE_BEGIN_PREFIX` break check inside `_parse_smb_conf()`

Keep `_read_smb_conf()`, `_get_default_config()`, and `_parse_smb_conf()` since they are still used
by effective-config inspection. Do not touch the `samba_backup_dir` runtime field.

## Acceptance criteria

- [ ] None of the removed methods or constants exist in SMBManager.
- [ ] `_parse_smb_conf()` no longer references `MANAGED_SHARE_BEGIN_PREFIX`.
- [ ] All existing SMBManager tests remain green.
- [ ] All existing samba layout tests remain green.
- [ ] `grep` for `MANAGED_SHARE_BEGIN_PREFIX` in non-test Python files returns no results.

## Blocked by

- 01-managed-share-user-helpers-owned-file-first
