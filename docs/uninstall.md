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

- SimpleSaferServer application files, scripts, and models
- SimpleSaferServer systemd services and timers
- app config, logs, task data, and user data
- the SimpleSaferServer-managed `/etc/fstab` entry
- Samba users synced from SimpleSaferServer accounts
- marker-wrapped SimpleSaferServer-managed Samba share blocks

The uninstaller does not remove shared system packages such as Samba, Python, or rclone. It also
leaves unmanaged or legacy untagged Samba share blocks in `/etc/samba/smb.conf` for safety.

If SimpleSaferServer configured Ubuntu Pro Livepatch, uninstall warns that Ubuntu Pro and Livepatch
state are retained. Review that host-level subscription/security state manually after uninstall.

If SimpleSaferServer changed the server hostname, uninstall warns with the original,
last SimpleSaferServer-applied, and current hostnames when available. The uninstaller
does not automatically change the hostname or `/etc/hosts` back because those are
host-level identity settings that may still be in use after the app is removed.

This process is irreversible. Back up anything important before uninstalling.
