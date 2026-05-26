# Uninstall cleans up legacy empty backup directory

## Parent

Planning/samba-post-review-fixes/PRD.md

## What to build

Older SimpleSaferServer installs created `/etc/samba/backups` for timestamped `smb.conf` backup
snapshots. Now that the backup-before-write pattern is removed, new installs no longer create or
populate this directory. The uninstall script should attempt to remove it if empty, but leave it
alone (silently) if it still contains old backup files the admin might want for recovery.

Add `rmdir /etc/samba/backups 2>/dev/null || true` to the uninstall script's Samba cleanup path.

## Acceptance criteria

- [ ] The uninstall script attempts `rmdir` on the legacy backup directory.
- [ ] A non-empty backup directory is left untouched (no error, no warning).
- [ ] An empty backup directory is removed.
- [ ] A missing backup directory does not produce an error.
- [ ] Existing uninstall tests pass.

## Blocked by

- Planning/samba-post-review-fixes/issues/01-remove-dead-samba-backup-dir-and-copy-config.md
