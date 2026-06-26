# Uninstallation Guide

To remove SimpleSaferServer from a server, run:

```bash
curl -fsSL https://sss.chrismin13.com/uninstall.sh | sudo bash
```

If you still have the repository folder, you can also run:

```bash
cd /path/to/SimpleSaferServer
sudo bash uninstall.sh
```

The uninstaller removes:

- SimpleSaferServer application files, CLI wrappers, and managed Python environment
- the `sss` terminal command wrapper
- the `sss-helper` privileged helper wrapper
- the `sss-helper` sudoers rule
- the SimpleSaferServer web and worker systemd services
- the `sss` service user and group, when the installer created them
- app config, logs, task data, and user data
- the SimpleSaferServer-managed `/etc/fstab` entry
- File Sharing-owned Samba accounts and Linux users recorded in the ownership manifest
- SimpleSaferServer include blocks in `/etc/samba/smb.conf`
- SimpleSaferServer-owned Samba files:
  `/etc/samba/simple_safer_server_globals.conf` and
  `/etc/samba/simple_safer_server_shares.conf`

The owned Samba files are deleted only when `<data>/ownership.json` records them as File Sharing
resources. If the ownership manifest does not prove that SSS owns those files, the uninstaller
leaves Samba config untouched. When ownership is recorded, the owned Samba files are deleted even
if `/etc/samba/smb.conf` is missing or has malformed SimpleSaferServer include markers. Malformed
markers prevent the uninstaller from rewriting `smb.conf`, but they do not block cleanup of files
that SimpleSaferServer owns by path. When markers are malformed, the uninstaller prints a warning
with exact manual recovery steps.

After successful cleanup, the uninstaller restarts `smbd` so the running service matches the
rewritten config. Active Samba file transfers will be interrupted. Discovery services (`nmbd`,
`wsdd2`) are not restarted because they are shared system services.

The uninstaller does not remove shared system packages or services such as Samba, `wsdd2`, Python,
or rclone. It also leaves unmanaged Samba share blocks in `/etc/samba/smb.conf` for safety.
New Cloud Backup config under `/etc/SimpleSaferServer/rclone` is removed with the app config.

This process is irreversible. Back up anything important before uninstalling.
