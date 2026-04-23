# Setup Wizard

The Setup Wizard walks through the first-time configuration of the system. The backup-drive portion has two different target types on purpose:

- Step 2 works on a whole disk when the user wants to prepare or erase a drive.
- Step 3 works on an NTFS partition when the user wants to mount and configure the backup destination.

That split is important because the safety checks are different.

## Navigation and Progress

- The progress bar shows the current step and allows moving between steps.
- Validation is inline for the form fields.
- Async buttons disable themselves while work is in progress.

## Step 1: Create Admin Account

- Enter the admin username.
- Enter the server name.
- Enter and confirm the password.
- On success, the wizard logs the user in and moves to the next step.
- That first account becomes the initial administrator for the web UI.
- Only administrator accounts can sign in to the management interface after setup.

## Step 2: Drive Format (Optional)

This step is disk-oriented.

- The selector shows disks, not partitions.
- The selector intentionally detects eligible non-system disks whether they are blank, already formatted, or currently formatted with the wrong filesystem.
- The unmount button unmounts every currently mounted partition that belongs to the selected disk.
- That unmount action only clears live mounts so the format step can proceed safely.
- It does not clear the saved backup-drive config and it does not remove the SimpleSaferServer-managed `/etc/fstab` entry.
- The format button creates a single partition if needed and formats that partition as NTFS.
- Formatting erases all existing data on the selected disk.

Why it works this way:

- Formatting is a whole-disk preparation step.
- Desktop automounters often mount child partitions such as `/dev/sdb1`, so the wizard checks for mounted child partitions before allowing formatting.
- This is a simple destructive preparation flow. It is not a partition resizer and it does not try to preserve or rearrange an existing multi-partition layout.

## Step 3: Drive Mount

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
- Advanced options allow changing the mount point and whether the managed `/etc/fstab` entry should be present.

Persistent backup-drive state changes only when the mount/configure step succeeds:

- `backup.mount_point`, `backup.uuid`, and `backup.usb_id` stay unchanged until a new backup-drive setup is applied successfully.
- The SimpleSaferServer-managed `/etc/fstab` entry is updated only when the new setup is applied.
- After the managed `/etc/fstab` entry changes, the app runs `systemctl daemon-reload` so `Check Mount` and the generated mount units immediately follow the new backup-drive definition.
- If the old backup drive is still the configured backup source and it remains connected, `Check Mount` may mount it again after an unmount-only step.

That NTFS-only scan is shared with the backup-drive rerun flow on Drive Health.
This is worth calling out because the setup wizard and the rerun flow need to
agree about which partitions are selectable, especially for already-mounted
`ntfs-3g` volumes that appear as `fuseblk`.

Boot behavior:

- The managed `/etc/fstab` entry uses `defaults,nofail`.
- That means the system should still boot if the backup drive is disconnected.

## Step 4: Backup Configuration

Choose one cloud-backup mode:

- Easy MEGA Cloud Backup
- Advanced rclone configuration

MEGA mode:

- Enter MEGA credentials.
- Connect and choose the target folder.
- The selected remote folder is shown before saving.

Advanced mode:

- Paste the rclone config.
- Enter the remote in `remote:/path` form.

## Step 5: Email Setup

- Enter the destination alert email address.
- Enter the From address used by the SMTP provider.
- Enter SMTP host, port, username, and password.

## Step 6: Schedule

- Set the backup time.
- Optionally set a bandwidth limit.
- Save to complete setup.
- Completing setup installs and activates the recurring systemd timers for mount checks, drive-health checks, cloud backups, and DDNS updates.
- The installer may generate those unit files earlier, but it keeps the timers inactive while `system.setup_complete` is false so persistent timers cannot run with placeholder setup values.

## Later Changes

If the backup drive changes after setup:

- use the advanced backup-drive section on the Drive Health page
- select the correct NTFS partition there
- rerun only the backup-drive configuration portion

That rerun flow is intentionally partition-oriented and does not behave like the whole-disk format step.
If the selected partition is still the live configured backup share, the rerun flow can temporarily disconnect SMB access before unmounting it.
