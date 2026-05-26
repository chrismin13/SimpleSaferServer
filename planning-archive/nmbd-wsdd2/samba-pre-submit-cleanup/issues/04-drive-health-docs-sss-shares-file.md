# Drive health docs reference SSS shares file

## What to build

Update `docs/drive_health.md` so the manual recovery section points operators to the correct
location for SimpleSaferServer-managed shares.

- Line 178 ("If the mount point changes, also check `/etc/samba/smb.conf`") should reference the
  Network File Sharing page and `/etc/samba/simple_safer_server_shares.conf`.
- Line 186 ("Samba share config: `/etc/samba/smb.conf`") should list
  `/etc/samba/simple_safer_server_shares.conf` as the managed share config, and note that
  `/etc/samba/smb.conf` is Samba's main config with SimpleSaferServer include wiring.

## Acceptance criteria

- [ ] `docs/drive_health.md` no longer tells operators to check `/etc/samba/smb.conf` as the share config for managed shares.
- [ ] The manual recovery section references `/etc/samba/simple_safer_server_shares.conf` and the Network File Sharing page.
- [ ] `/etc/samba/smb.conf` is still mentioned as Samba's main config file where appropriate.

## Blocked by

None - can start immediately.
