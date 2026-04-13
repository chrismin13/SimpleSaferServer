# Drive Health

The Drive Health page is the main place to inspect the configured backup drive and to rerun backup-drive configuration if the physical backup device changes.

It combines:

- SMART data and the local failure-prediction result
- HDSentinel health and performance reporting

## Features

- Run a manual health refresh from the page.
- View the SMART prediction result and probability.
- View missing SMART attributes that fell back to defaults.
- View the HDSentinel device snapshot.
- Enable or disable HDSentinel monitoring and change alert settings.
- Download SMART telemetry as CSV.

## SMART Error Reporting

The SMART prediction path uses `smartctl` JSON output when the installed
`smartctl` version supports `-j`.

- The "upgrade smartmontools" warning is reserved for the explicit case where
  `smartctl -h` shows that JSON output is unavailable.
- If `smartctl` advertises JSON support but the actual SMART read still fails,
  the app preserves the original `smartctl` error instead. This matters because
  USB bridges, controller quirks, and device read failures can all break SMART
  collection even on newer smartmontools versions.

That split is easy to forget later because both cases may surface during the
same troubleshooting session, but they need different remediation.

## Re-running Backup Drive Setup

Use the advanced backup-drive section only when:

- the backup drive was replaced
- the original UUID or USB ID was detected incorrectly
- the app needs to be pointed at the correct backup partition again

This flow is partition-oriented.

- The selector shows NTFS partitions.
- The selector uses the same NTFS-partition scan as setup wizard step 3.
- If `lsblk` reports a mounted `ntfs-3g` partition as `fuseblk`, the app double-checks the on-disk type with `blkid` before showing it.
- Partitions reported as `ntfs3`, `ntfs-3g`, or confirmed-NTFS `fuseblk` are treated as NTFS backup targets by the picker.
- The unmount action unmounts only the exact selected partition.
- That unmount action only clears the live mount so the selected partition can be validated and configured again.
- If the selected partition is still the configured backup drive and it is currently mounted at the managed backup mount point, the app first disconnects SMB access and stops the related background tasks so the unmount is not blocked by busy share handles.
- The app intentionally does not escalate to that broader SMB-safe path based on UUID alone, because cloned replacement disks can legitimately share a filesystem UUID and would make the selected physical device ambiguous.
- The configure action mounts only the exact selected partition.

This is different from setup wizard step 2, which is disk-oriented for formatting.

It is also different from the main Dashboard `Unmount Drive` action.

- Dashboard unmount is temporary for the configured backup drive.
- If that drive stays connected, SimpleSaferServer may remount it automatically during the next scheduled `Check Mount` run.
- The Drive Health unmount button exists to clear the selected partition so the rerun flow can mount and validate the exact partition you picked.
- When the selected partition is the live configured backup share, Drive Health uses the same SMB-safe unmount sequence as Dashboard, but it does not power the disk down because the next step is usually to mount and validate it again.
- The Drive Health unmount button does not clear the stored backup `mount_point`, `uuid`, `usb_id`, or managed `/etc/fstab` entry by itself.

## What the Rerun Flow Updates

- the stored backup `mount_point`
- the stored backup `uuid`
- the stored backup `usb_id`
- the SimpleSaferServer-managed `/etc/fstab` entry for the backup drive
- the Samba backup share path if the mount point changed

The rerun flow always refreshes the managed `/etc/fstab` entry with `defaults,nofail`.
After rewriting the managed `/etc/fstab` entry, the app also runs `systemctl daemon-reload` so the next `Check Mount` run sees the updated systemd-generated mount units immediately.

Persistent backup-drive state changes happen only when the rerun configure step succeeds.
That separation is intentional because a failed replacement attempt should still be able to fall back to the previously configured backup drive.

## What "SimpleSaferServer-managed" Means

The app only manages the `/etc/fstab` line for the backup drive that ends with:

```text
# SimpleSaferServer managed backup drive
```

The app does not treat unrelated `/etc/fstab` lines as its own unless they use that marker or the older legacy marker.

## Safety Rules

- The rerun flow does not edit unrelated `/etc/fstab` entries.
- If the app finds multiple managed entries, it stops and asks for manual cleanup.
- If a non-SimpleSaferServer entry already uses the same UUID or mount point, it stops and asks for manual cleanup.
- If the selected partition is already mounted, it stops and asks the user to unmount it first.

## Manual Recovery

If you need to inspect or repair the backup-drive configuration manually, start here:

```bash
sudo awk '1' /etc/SimpleSaferServer/config.conf
sudo grep -n 'SimpleSaferServer' /etc/fstab
lsblk -f
sudo blkid -s TYPE -o value /dev/sdX1
sudo blkid -s UUID -o value /dev/sdX1
lsusb
sudo findmnt --verify
```

Manual recovery rules:

- Update `/etc/SimpleSaferServer/config.conf` only if you know the correct `mount_point`, `uuid`, and `usb_id`.
- Update only the SimpleSaferServer-managed `/etc/fstab` entry.
- Run `sudo systemctl daemon-reload` after manually changing `/etc/fstab` so systemd forgets the old generated mount unit state.
- If the mount point changes, also check `/etc/samba/smb.conf`.
- Do not modify unrelated `/etc/fstab` entries.
- Back up `/etc/fstab` before editing it manually.

Important file locations:

- App config: `/etc/SimpleSaferServer/config.conf`
- Managed mount entry: `/etc/fstab`
- Samba share config: `/etc/samba/smb.conf`

Example managed `/etc/fstab` entry:

```fstab
UUID=2CD49023D48FED80    /media/backup    ntfs-3g    defaults,nofail    0    0 # SimpleSaferServer managed backup drive
```

After manual changes, verify the result:

Restarting `smbd` and `nmbd` disconnects anyone who is currently connected to a share, so active file copies or other SMB activity will drop.

```bash
sudo findmnt --verify
sudo mkdir -p /media/backup
sudo systemctl daemon-reload
sudo mount -a
sudo systemctl restart smbd nmbd simple_safer_server_web.service
```
