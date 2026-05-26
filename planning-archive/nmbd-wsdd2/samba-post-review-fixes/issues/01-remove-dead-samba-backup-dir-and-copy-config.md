# Remove dead `samba_backup_dir` and `copy_config` code

## Parent

Planning/samba-post-review-fixes/PRD.md

## What to build

Remove the unused backup infrastructure left over from the old backup-before-write pattern that was
replaced by the file-path ownership model:

- Remove `samba_backup_dir` from the runtime dataclass, its resolution helper, the `get_runtime()`
  construction calls, and the `mkdir` that creates it on startup.
- Remove `copy_config` from `SmbCommandAdapter` and its unit test.
- Remove `samba_backup_dir` from all test fixtures that set it on fake runtimes.

This is pure dead code removal. No behavioral change to the application or uninstall script.

## Acceptance criteria

- [ ] `samba_backup_dir` attribute no longer exists on the runtime dataclass.
- [ ] No `mkdir` call creates a backup directory on startup.
- [ ] `copy_config` method no longer exists on `SmbCommandAdapter`.
- [ ] `test_smb_command_adapter.py` no longer tests `copy_config`.
- [ ] All test fixtures compile without referencing `samba_backup_dir`.
- [ ] All existing tests pass.

## Blocked by

None - can start immediately.
