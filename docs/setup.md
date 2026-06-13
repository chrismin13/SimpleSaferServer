# Setup Wizard

The Setup Wizard walks through the first-time configuration of the system. The storage portion now has two paths:

- **Prepare a drive for SimpleSaferServer**: the app formats or mounts a disk partition and manages how it is mounted.
- **Use an existing folder**: the user provides a folder that already exists on the server.

That split is important because a cloud backup sync can delete remote files if the local storage folder is unexpectedly empty. SimpleSaferServer records a small marker file in the selected storage location and checks it before cloud backups run.

## Navigation and Progress

- The progress bar shows the current step and allows moving between steps.
- Validation is inline for the form fields.
- Async buttons disable themselves while work is in progress.

## Step 1: Create Admin Account

- Enter the admin username.
- Enter the server name. This is the name you use to find the server on your
  network, and it appears in alert emails.
- Server names may contain letters, numbers, and hyphens. They cannot contain
  spaces or start/end with a hyphen.
- Enter and confirm the password.
- On success, the wizard logs the user in and moves to the next step.
- That first account becomes the initial administrator for the web UI.
- Only administrator accounts can sign in to the management interface after setup.

## Step 2: Storage Location

Choose where SimpleSaferServer should store files.

SimpleSaferServer creates a default network share named `backup`. This is the folder people on your network copy files into from their computers, and it points at the storage location chosen here.

Use **Prepare a drive for SimpleSaferServer** when you want the app to handle the backup disk. This is the simplest path for the original one-drive setup.

Use **Use an existing folder** when the storage is already handled outside SimpleSaferServer. That folder can be on a RAID array, a pooled filesystem, a manually mounted disk, a server folder, or any other local path that is already prepared.

When an existing folder is selected:

- SimpleSaferServer stores that path as the storage location.
- SimpleSaferServer creates `.simple-safer-server/storage.json` inside that folder.
- SimpleSaferServer does not add an `/etc/fstab` entry for it.
- SimpleSaferServer does not mount or unmount it from the Dashboard.
- The user or the operating system is responsible for making sure it is available after reboot.

The marker file is not backup data. It exists so the app can tell the difference between the intended storage location and an empty folder that only exists because a disk, pool, or remote mount failed to appear.

## Step 3: Prepare Drive

This step is shown for users who chose to let SimpleSaferServer prepare a drive.

### Drive Format

This step is disk-oriented.

- The selector shows disks, not partitions.
- The selector intentionally detects eligible non-system disks whether they are blank, already formatted, or currently formatted with the wrong filesystem.
- The unmount button unmounts every currently mounted partition that belongs to the selected disk.
- That unmount action only clears live mounts so the format step can proceed safely.
- It does not clear the saved backup-drive config and it does not remove the SimpleSaferServer-managed `/etc/fstab` entry.
- The format button removes the existing drive layout, creates one large backup partition, and formats that partition as NTFS.
- Formatting erases all existing data on the selected disk.

Why it works this way:

- Formatting is a whole-disk preparation step.
- Desktop automounters often mount child partitions such as `/dev/sdb1`, so the wizard checks for mounted child partitions before allowing formatting.
- This is a simple destructive preparation flow. It does not try to preserve or rearrange an existing multi-partition layout.

### Drive Mount

This step is partition-oriented.

- The selector shows NTFS partitions, not whole disks.
- The selector uses a dedicated NTFS-partition scan instead of the broader step-2 disk scan.
- If a mounted `ntfs-3g` partition shows up from `lsblk` as `fuseblk`, the wizard verifies the underlying on-disk type with `blkid` before treating it as NTFS.
- Partitions reported as `ntfs3`, `ntfs-3g`, or confirmed-NTFS `fuseblk` are all exposed to the wizard as NTFS mount targets.
- Drive labels prefer `lsblk` transport data such as `TRAN=usb`, with `RM` and `HOTPLUG` as fallbacks, so removable backup targets are not mislabeled as internal disks.
- The unmount button unmounts only the exact selected partition.
- That unmount action is temporary preparation for this step. It does not deconfigure the old backup drive by itself.
- If the exact unmount fails and the selected partition is still the live configured backup drive mounted at the managed backup mount point, the wizard offers a second explicit SMB-safe retry that may temporarily stop SMB access and the related background backup tasks before retrying the unmount.
- The wizard intentionally does not offer that broader retry based on UUID alone, because cloned replacement disks can legitimately share a filesystem UUID and would make the safety check ambiguous.
- The mount button mounts that selected NTFS partition at the chosen mount point.
- Advanced options allow changing the mount point.
- A successful mount step writes the managed `/etc/fstab` entry so the backup drive can be remounted at boot and by scheduled mount checks.
- A successful mount step also creates the storage marker file at `.simple-safer-server/storage.json` inside the configured storage location.

Persistent backup-drive state changes only when the mount/configure step succeeds:

- `backup.mount_point`, `backup.uuid`, and `backup.usb_id` stay unchanged until a new backup-drive setup is applied successfully.
- The SimpleSaferServer-managed `/etc/fstab` entry is updated only when the new setup is applied.
- After the managed `/etc/fstab` entry changes, the app runs `systemctl daemon-reload` so `Check Mount` and the generated mount units immediately follow the new backup-drive definition.
- If the old backup drive is still the configured backup source and it remains connected, `Check Mount` may mount it again after an unmount-only step.

That NTFS-only scan is shared with the prepared-drive setup flow on the Storage page.
This is worth calling out because the setup wizard and the later Storage page flow need to
agree about which partitions are selectable, especially for already-mounted
`ntfs-3g` volumes that appear as `fuseblk`.

Boot behavior:

- The managed `/etc/fstab` entry uses `ntfs-3g` with `defaults,nofail`.
- That means the system should still boot if the backup drive is disconnected.

## Step 4: Cloud Backup

Cloud Backup is optional.

Choose one cloud-backup mode:

- Easy MEGA Cloud Backup
- Advanced rclone configuration

You can also skip cloud backup. This is useful when:

- the server is only used for local network backups
- another tool already handles off-site backup
- you want to finish setup first and configure cloud backup later

SimpleSaferServer saves cloud backup as explicitly enabled or disabled. If that setting is missing or invalid, scheduled cloud backup fails and alerts the administrator instead of guessing.

MEGA mode:

- Enter MEGA credentials.
- Connect and choose the target folder.
- The selected remote folder is shown before saving.

Advanced mode:

- Paste the rclone config.
- Enter the remote in `remote:/path` form.

Before every cloud backup, SimpleSaferServer checks the storage marker and confirms it can read and write in the storage location. If those checks fail, the backup does not run. This avoids syncing an empty or broken local folder to the cloud and accidentally deleting the remote copy.

## Step 5: Email Setup

- Enter the destination alert email address.
- Enter the From address used by the SMTP provider.
- Enter SMTP host, TCP port (1-65535), username, and password.

## Step 6: Schedule

- Set the backup time. The setup wizard saves two-digit 24-hour `HH:MM` values such as `03:00`
  or `23:30`.
- Optionally set a bandwidth limit.
- Save to complete setup.
- Completing setup installs the recurring systemd timers.
- The mount-check timer is enabled only when SimpleSaferServer manages the prepared drive.
- The cloud-backup timer is enabled only when cloud backup is configured.
- Drive-health, app-update, and DDNS timers are enabled after setup.
- Setup and later unit refreshes preserve active SimpleSaferServer Disable Schedule records so
  regenerating unit files does not silently re-enable a disabled timer.
- The cloud backup timer stays on the configured time.
- When the prepared-drive mount check is enabled, it runs 4 minutes before backup.
- The generated drive-health check runs 2 minutes before backup. This spacing gives the mount check time to finish before health probes the drive when SimpleSaferServer manages the drive, even with systemd's small randomized delay.
- The installer may generate those unit files earlier, but it keeps the timers inactive while `system.setup_complete` is false so persistent timers cannot run with placeholder setup values.

## Later Changes

If the storage location changes after setup:

- use the Storage page
- choose a new existing folder, or rerun the prepared-drive setup there
- check that the default `backup` network share still points to the intended folder

The prepared-drive rerun flow is intentionally partition-oriented and does not behave like the whole-disk format step.
If the selected partition is still the live configured backup share, the rerun flow can temporarily disconnect SMB access before unmounting it.
