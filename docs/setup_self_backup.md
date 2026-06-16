# Setup Self-Backup

SimpleSaferServer can back up the files that its setup flow owns. This helps you recover the web app setup after a reinstall without copying the whole server.

This is not a full system backup.

## What It Includes

The archive includes these files when they exist:

- SimpleSaferServer config from `/etc/SimpleSaferServer`
- the user database, secret key, encrypted secrets, alerts, and disabled timer records
- rclone config from root's rclone config folder
- msmtp config from `/etc/msmtprc`
- SimpleSaferServer-owned Samba include files

It does not include `/etc/fstab`. That is intentional. Restoring an old mount table can make a server fail to boot or mount the wrong disk.

It also does not include the full backup drive data, operating system files, package state, or unmanaged Samba config.

## Automatic Backup

After setup is complete, SimpleSaferServer creates a self-backup on the configured backup drive.

It also installs a daily `setup_self_backup.timer`. This timer runs one minute before the normal cloud backup time, so the fresh self-backup archive can be copied to your cloud target by the normal cloud backup.

Archives are stored here on the mounted backup drive:

```text
SimpleSaferServer-self-backups/
```

Only the newest 30 archives are kept by the scheduled command.

## Manual Backup

Run this as root:

```bash
sudo /opt/SimpleSaferServer/.venv/bin/python /opt/SimpleSaferServer/scripts/setup_self_backup.py create
```

To list existing archives:

```bash
sudo /opt/SimpleSaferServer/.venv/bin/python /opt/SimpleSaferServer/scripts/setup_self_backup.py list
```

To write to a specific mounted drive path:

```bash
sudo /opt/SimpleSaferServer/.venv/bin/python /opt/SimpleSaferServer/scripts/setup_self_backup.py create --destination /media/backup
```

## Restore During Setup

Use this after reinstalling SimpleSaferServer, before finishing the setup wizard.

1. Mount the backup drive.
2. Find the archive under `SimpleSaferServer-self-backups/`.
3. Restore it:

```bash
sudo /opt/SimpleSaferServer/.venv/bin/python /opt/SimpleSaferServer/scripts/setup_self_backup.py restore /media/backup/SimpleSaferServer-self-backups/setup-self-backup-YYYYMMDDTHHMMSSZ.tar.gz
```

By default, restore sets `system.setup_complete` to `false`. This lets the setup wizard reinstall services, timers, Samba share setup, and the managed backup-drive setup for the current machine.

After the restore, open the setup wizard and finish setup. Check the backup drive step carefully. The self-backup does not restore `/etc/fstab`, so the current backup drive still needs to be mounted and registered by setup.

## Restore On A Running Install

The restore command is mainly meant for reinstall recovery. If you run it on an already working install, restart SimpleSaferServer afterwards so the web app reloads the restored files.

Only use `--preserve-setup-complete` when you understand that setup will not be forced to rerun service and timer installation:

```bash
sudo /opt/SimpleSaferServer/.venv/bin/python /opt/SimpleSaferServer/scripts/setup_self_backup.py restore /path/to/archive.tar.gz --preserve-setup-complete
```
