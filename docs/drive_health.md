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
- If `lsblk` reports a mounted `ntfs-3g` partition as `fuseblk`, the app double-checks the on-disk type with `blkid` before showing it.
- The unmount action unmounts only the exact selected partition.
- The configure action mounts only the exact selected partition.

This is different from setup wizard step 2, which is disk-oriented for formatting.

## What the Rerun Flow Updates

- the stored backup `mount_point`
- the stored backup `uuid`
- the stored backup `usb_id`
- the SimpleSaferServer-managed `/etc/fstab` entry for the backup drive
- the Samba backup share path if the mount point changed

The rerun flow always refreshes the managed `/etc/fstab` entry with `defaults,nofail`.

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

```bash
sudo findmnt --verify
sudo mkdir -p /media/backup
sudo mount -a
sudo systemctl restart smbd nmbd simple_safer_server_web.service
```
