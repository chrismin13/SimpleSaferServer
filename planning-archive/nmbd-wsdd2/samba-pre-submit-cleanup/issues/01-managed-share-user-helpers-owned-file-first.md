# Managed-share user helpers use owned-file lookup first

## What to build

Change `_get_managed_share_or_raise()` so it checks the SimpleSaferServer-owned shares file before
touching Effective Samba Config inspection. If the share is found in the owned file, return it
immediately. Only inspect unmanaged shares afterward to produce the "not managed by
SimpleSaferServer" error when the share exists outside the owned file. If unmanaged inspection also
fails, fall back to a generic "share not found" error.

This makes `get_share_users()` and `update_share_users()` resilient to broken admin-owned Samba
includes, since they only operate on shares SimpleSaferServer already owns.

## Acceptance criteria

- [ ] `get_share_users()` succeeds for an existing SimpleSaferServer-Managed Share when Effective Config inspection would fail.
- [ ] `update_share_users()` succeeds for an existing SimpleSaferServer-Managed Share when Effective Config inspection would fail.
- [ ] `get_share_users()` raises a clear "not managed" error for an unmanaged share name when inspection succeeds.
- [ ] `get_share_users()` raises a clear "not found" error for a share that does not exist anywhere.
- [ ] All existing SMBManager tests remain green.

## Blocked by

None - can start immediately.
