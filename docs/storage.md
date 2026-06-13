# Storage

The Storage page controls where SimpleSaferServer stores backup files.

There are two storage modes:

- **Prepared drive**: SimpleSaferServer mounts and manages one selected drive partition.
- **Existing folder**: an administrator provides a folder that already exists on the server.

## Prepared Drive

Use this mode when you want SimpleSaferServer to handle the backup disk.

In this mode the app:

- mounts the selected partition at the configured mount point
- writes the SimpleSaferServer-owned `/etc/fstab` entry
- enables the scheduled mount check
- allows mount and unmount actions from the Dashboard
- creates the storage marker file inside the storage folder

This is the simplest mode for the original one-drive setup.

## Existing Folder

Use this mode when the storage is already managed outside SimpleSaferServer.

Examples include:

- a RAID array
- a ZFS or Btrfs pool
- a mergerfs folder
- a SnapRAID data disk or pooled folder
- a manually mounted disk
- a folder on the server's main filesystem

In this mode the app:

- stores the folder path in the app config
- creates `.simple-safer-server/storage.json` inside that folder
- updates the default `backup` network share to point at the folder
- checks that the folder is still available before cloud backup runs

In this mode the app does not:

- format the disk
- create a RAID or pool
- add an `/etc/fstab` entry
- mount the folder after reboot
- unmount the folder from the Dashboard

The administrator or the operating system is responsible for making sure the folder is available.

## The Storage Marker

SimpleSaferServer writes this marker file inside the selected storage location:

```text
.simple-safer-server/storage.json
```

The marker contains a random storage ID that is also saved in the app config.

The marker exists because cloud backup uses `rclone sync`. If the local storage folder is empty because a disk, pool, or mount failed, syncing that empty folder could delete files from the cloud destination. The marker gives the app something stable to check before it starts a cloud backup.

Before each cloud backup, the app checks that:

- the marker exists
- the marker ID matches the saved config
- the marker can be read
- the storage folder can be written to
- a small test file can be read back
- the small test file can be deleted

If any of those checks fail, the cloud backup is blocked.

## Repairing The Marker

Use marker repair only after confirming that the folder shown on the Storage page is the correct storage location.

Marker repair rewrites `.simple-safer-server/storage.json` with the storage ID saved in the app config. It does not repair missing data, mount a disk, create a pool, or choose a different folder.

## Drive Health

Drive Health is separate from Storage.

Drive Health checks disk health and shows HDSentinel or SMART information. Storage decides which folder SimpleSaferServer uses for backups and which location must pass the cloud-backup safety checks.

By default, SimpleSaferServer tries to monitor all drives HDSentinel reports. If a drive cannot report health, the page shows the information that is available instead of treating the storage setup as broken.
