# Storage

The Storage page controls where SimpleSaferServer stores backup files.

SimpleSaferServer keeps a default network share named `backup` pointed at the selected storage location. This is the folder people on your network copy files into from their computers.

The page shows the current storage location, the active storage mode, and a passive storage status. It does not run the full cloud-backup safety check just because the page opened. Configuration changes are started from the Storage actions card:

- **Managed drive**: SimpleSaferServer mounts and manages one selected drive partition.
- **Existing folder**: an administrator provides a folder that already exists on the server.

The top help band is rendered from the Storage module contract in
`simple_safer_server/modules/storage/module.py`. Keep the purpose text, setup note, field help, and
drive warnings there so the Web UI, setup flow, CLI, and docs can share the same wording.

The Storage actions card keeps repair actions separate from configuration changes. Safety checks stay visible beside the storage actions on wide screens and move below them on narrower screens.

## Passive Status And Sleeping Drives

The Storage page and Dashboard avoid read-write safety checks during normal page loads. This is deliberate.

Many backup drives are allowed to spin down when idle. Reading the storage marker or writing a test file can wake a sleeping drive. A page view should not do that.

Automatic page status is therefore passive:

- it reads the saved app config
- for managed drives, it checks mount state from the operating system mount table
- it may show disk usage when the operating system can provide it
- it does not read the marker file
- it does not write the test file
- it does not list the storage folder

Disk usage stays visible because it uses the operating system's filesystem statistics path. On Linux, `statvfs()` and `statfs()` return information about a mounted filesystem, and `/proc/mounts` lists mounted filesystems from kernel state:

- `statvfs(3)`: `https://man7.org/linux/man-pages/man3/statvfs.3.html`
- `statfs(2)`: `https://man7.org/linux/man-pages/man2/statfs.2.html`
- `/proc/pid/mounts`: `https://man7.org/linux/man-pages/man5/proc_pid_mounts.5.html`

That does not prove every filesystem and every drive firmware will stay asleep forever, but it is much less direct than opening the storage marker or creating a test file. In practice, disk usage has not been the wake-up problem for SimpleSaferServer. The read-write probe has.

Use **Run safety check** when you want the full check from the Storage page. That action may wake the drive.

## Managed Drive

Use this mode when you want SimpleSaferServer to handle the backup disk.

Managed-drive setup uses normal host disk tools such as `lsblk`, `blkid`, `sfdisk`, `mkfs.ntfs`,
and `ntfs-3g`. The Storage module reports these as optional tools because they are only needed for
the advanced managed-drive path. Existing-folder storage does not need them.

In this mode the app:

- mounts the selected partition at the configured mount point
- writes the SimpleSaferServer-owned `/etc/fstab` entry
- enables the scheduled mount check
- allows mount actions and the allowlisted `storage.managed-unmount` helper action from the Dashboard
- creates the storage marker file inside the storage folder

This is the simplest mode for the original one-drive setup.

## Ownership Records

Applying the Storage module records only the app-owned `storage` config section. The exact storage
marker and `/etc/fstab` records are added later by the setup path that actually writes them:

- existing-folder setup records the exact `.simple-safer-server/storage.json` marker path after the marker is written
- managed-drive setup records the exact marker path and the exact managed `/etc/fstab` entry after the helper writes them

This keeps existing-folder setup from claiming ownership of an `/etc/fstab` entry that SSS did not
create.

### Change Managed Drive

Use **Change managed drive** on the Storage page when replacing the managed backup disk.

The change page has two sections:

- **Format a drive** lists non-system disks that can be set up for backup storage. The page asks the allowlisted `storage.format` helper action to delete the selected disk's files and partitions, create one NTFS partition, and leave the current SimpleSaferServer storage setting unchanged.
- **Use an NTFS partition** lists NTFS partitions that can become the managed backup drive. This is the only section that changes SimpleSaferServer storage.

Unmount actions on the change page are temporary setup steps. Unmounting a selected disk or partition does not clear the saved storage path, configured UUID, `/etc/fstab` entry, marker file, or worker schedule.

The current storage configuration changes only after **Use This Drive** succeeds. On success, SimpleSaferServer:

- mounts the selected NTFS partition at the chosen mount point
- writes the SimpleSaferServer-managed `/etc/fstab` entry
- updates `backup.mount_point`, `backup.uuid`, and `backup.usb_id`
- updates the default `backup` network share path
- creates the storage marker file in the selected storage location
- refreshes the task config consumed by the worker

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
- mount or unmount the folder from the Dashboard

The administrator or the operating system is responsible for making sure the folder is available.

Use **Choose folder** on the Storage page to open the existing-folder change page. The path can be typed by hand, or selected with **Browse**. The picker shows folders and files in the current server path so the administrator can see what is already there, but only folders can be opened or selected.

The page saves the new folder only after **Use This Folder** succeeds. On success, SimpleSaferServer stores the folder path, updates the default `backup` share, creates the storage marker, and validates the worker schedule.

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

The same full check also runs when an administrator chooses a new storage target, repairs the marker, or manually runs **Run safety check**. Those actions are allowed to touch the drive because the administrator asked for storage work or the cloud backup is about to read the drive anyway.

## Repairing The Marker

Use marker repair only after confirming that the folder shown on the Storage page is the correct storage location.

Marker repair rewrites `.simple-safer-server/storage.json` with the storage ID saved in the app config. It does not repair missing data, mount a disk, create a pool, or choose a different folder.

## Drive Health

Drive Health is separate from Storage.

Drive Health checks disk health and shows HDSentinel or SMART information. Storage decides which folder SimpleSaferServer uses for backups and which location must pass the cloud-backup safety checks.

By default, SimpleSaferServer tries to monitor all drives HDSentinel reports. If a drive cannot report health, the page shows the information that is available instead of treating the storage setup as broken.
