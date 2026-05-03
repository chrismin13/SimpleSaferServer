# 0024 Config Manager Locked Updates

## Summary

- Removed the generic `ConfigManager.save_config()` snapshot write path.
- Normal config writes now lock `config.conf.lock`, re-read `config.conf`, apply the intended
  mutation, atomically replace `config.conf`, and refresh in-process state from the written parser.

## Decisions

- Use a stable sidecar lock because `config.conf` is replaced with `os.replace`; locking the target
  file can leave concurrent processes locking different inodes.
- Keep full config replacement only as an explicit `replace_config()` operation for migration/import
  workflows where replacing the entire INI file is the intended behavior.
- Default config creation is locked and create-if-missing so concurrent first-start workers do not
  replace an existing config with defaults.

## Verification

- Added focused `ConfigManager` tests for stale-manager writes, first-run default creation, and
  explicit full replacement.
