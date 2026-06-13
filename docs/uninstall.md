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

- SimpleSaferServer application files, scripts, and managed Python environment
- SimpleSaferServer systemd services and timers
- app config, logs, task data, and user data
- Disable Schedule restore timer state, helper script, and disabled-timer data
- the SimpleSaferServer-managed `/etc/fstab` entry
- Samba users synced from SimpleSaferServer accounts
- SimpleSaferServer include blocks in `/etc/samba/smb.conf`
- SimpleSaferServer-owned Samba files:
  `/etc/samba/simple_safer_server_globals.conf` and
  `/etc/samba/simple_safer_server_shares.conf`

The owned Samba files are deleted even if `/etc/samba/smb.conf` is missing or has malformed
SimpleSaferServer include markers. Malformed markers prevent the uninstaller from rewriting
`smb.conf`, but they do not block cleanup of files that SimpleSaferServer owns by path. When
markers are malformed, the uninstaller prints a warning with exact manual recovery steps.

After successful cleanup, the uninstaller restarts `smbd` so the running service matches the
rewritten config. Active Samba file transfers will be interrupted. Discovery services (`nmbd`,
`wsdd2`) are not restarted because they are shared system services.

The uninstaller does not remove shared system packages or services such as Samba, `wsdd2`, Python,
or rclone. It also leaves unmanaged Samba share blocks in `/etc/samba/smb.conf` for safety.

If SimpleSaferServer configured Ubuntu Pro Livepatch, uninstall warns that Ubuntu Pro and Livepatch
state are retained. Review that host-level subscription/security state manually after uninstall.

If SimpleSaferServer changed the server hostname, uninstall warns with the original,
last SimpleSaferServer-applied, and current hostnames when available. The uninstaller
does not automatically change the hostname or `/etc/hosts` back because those are
host-level identity settings that may still be in use after the app is removed.

This process is irreversible. Back up anything important before uninstalling.
