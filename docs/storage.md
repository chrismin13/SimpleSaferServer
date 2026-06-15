# Storage

The Storage page controls where SimpleSaferServer stores backup files.

SimpleSaferServer keeps a default network share named `backup` pointed at the selected storage location. This is the folder people on your network copy files into from their computers.

The page shows the current storage location, the active storage mode, and whether the cloud-backup safety checks are passing. Configuration changes are started from the Storage actions card:

- **Managed drive**: SimpleSaferServer mounts and manages one selected drive partition.
- **Existing folder**: an administrator provides a folder that already exists on the server.

The Storage actions card keeps repair actions separate from configuration changes. Safety checks stay visible beside the storage actions on wide screens and move below them on narrower screens.

## Managed Drive

Use this mode when you want SimpleSaferServer to handle the backup disk.

In this mode the app:

- mounts the selected partition at the configured mount point
- writes the SimpleSaferServer-owned `/etc/fstab` entry
- enables the scheduled mount check
- allows mount and unmount actions from the Dashboard
- creates the storage marker file inside the storage folder

This is the simplest mode for the original one-drive setup.

### Change Managed Drive

Use **Change managed drive** on the Storage page when replacing the managed backup disk.

The change page has two sections:

- **Format a drive** lists non-system disks that can be set up for backup storage. Formatting deletes the selected disk's files and partitions, creates one NTFS partition, and leaves the current SimpleSaferServer storage setting unchanged.
- **Use an NTFS partition** lists NTFS partitions that can become the managed backup drive. This is the only section that changes SimpleSaferServer storage.

Unmount actions on the change page are temporary setup steps. Unmounting a selected disk or partition does not clear the saved storage path, configured UUID, `/etc/fstab` entry, marker file, or timers.

The current storage configuration changes only after **Use This Drive** succeeds. On success, SimpleSaferServer:

- mounts the selected NTFS partition at the chosen mount point
- writes the SimpleSaferServer-managed `/etc/fstab` entry
- updates `backup.mount_point`, `backup.uuid`, and `backup.usb_id`
- updates the default `backup` network share path
- creates the storage marker file in the selected storage location
- refreshes the generated systemd services and timers

If an administrator leaves the change page after formatting or unmounting but before using a partition, the previous storage configuration remains in place.

The advanced options on the change page allow changing the mount point and choosing the NTFS driver. `ntfs-3g` is the default. `ntfs3` is available for systems where the in-kernel driver is preferred.

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

Use **Choose folder** on the Storage page to open the existing-folder change page. The path can be typed by hand, or selected with **Browse**. The picker shows folders and files in the current server path so the administrator can see what is already there, but only folders can be opened or selected.

The page saves the new folder only after **Use This Folder** succeeds. On success, SimpleSaferServer stores the folder path, updates the default `backup` share, creates the storage marker, and refreshes generated task timers.

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
- a managed drive's mounted filesystem UUID matches the configured drive UUID

If any of those checks fail, the cloud backup is blocked.

## Repairing The Marker

Use marker repair only after confirming that the folder shown on the Storage page is the correct storage location.

Marker repair rewrites `.simple-safer-server/storage.json` with the storage ID saved in the app config. It does not repair missing data, mount a disk, create a pool, or choose a different folder.

## Drive Health

Drive Health is separate from Storage.

Drive Health checks disk health and shows HDSentinel or SMART information. Storage decides which folder SimpleSaferServer uses for backups and which location must pass the cloud-backup safety checks.

By default, SimpleSaferServer tries to monitor all drives HDSentinel reports. If a drive cannot report health, the page shows the information that is available instead of treating the storage setup as broken.
