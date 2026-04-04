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

## Step 2: Drive Format (Optional)

This step is disk-oriented.

- The selector shows disks, not partitions.
- The unmount button unmounts every currently mounted partition that belongs to the selected disk.
- The format button creates a single partition if needed and formats that partition as NTFS.
- Formatting erases all existing data on the selected disk.

Why it works this way:

- Formatting is a whole-disk preparation step.
- Desktop automounters often mount child partitions such as `/dev/sdb1`, so the wizard checks for mounted child partitions before allowing formatting.

## Step 3: Drive Mount

This step is partition-oriented.

- The selector shows NTFS partitions, not whole disks.
- If a mounted `ntfs-3g` partition shows up from `lsblk` as `fuseblk`, the wizard verifies the underlying on-disk type with `blkid` before treating it as NTFS.
- The unmount button unmounts only the exact selected partition.
- The mount button mounts that selected NTFS partition at the chosen mount point.
- Advanced options allow changing the mount point and whether the managed `/etc/fstab` entry should be present.

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

## Later Changes

If the backup drive changes after setup:

- use the advanced backup-drive section on the Drive Health page
- select the correct NTFS partition there
- rerun only the backup-drive configuration portion

That rerun flow is intentionally partition-oriented and does not behave like the whole-disk format step.
