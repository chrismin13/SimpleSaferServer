# Drive Health

The Drive Health page is the main place to inspect the configured backup drive and to rerun backup-drive configuration if the physical backup device changes.

It combines:

- SMART data and, when the optional Python prediction dependencies can load,
  the local failure-prediction result
- HDSentinel health and performance reporting

## Features

- Run a manual health refresh from the page.
- Refresh the Dashboard Drive Health tile explicitly when you want a live probe from the overview.
- View the SMART prediction result and probability when prediction is available.
- View missing SMART attributes that fell back to defaults.
- View the HDSentinel device snapshot.
- Enable or disable HDSentinel monitoring and change alert settings.
- Download SMART telemetry as CSV.

## SMART Error Reporting

SMART collection uses `smartctl` JSON output when the installed `smartctl`
version supports `-j`.

- The "upgrade smartmontools" warning is reserved for the explicit case where
  `smartctl -h` shows that JSON output is unavailable.
- If `smartctl` advertises JSON support but the actual SMART read still fails,
  the app preserves the original `smartctl` error instead. This matters because
  USB bridges, controller quirks, and device read failures can all break SMART
  collection even on newer smartmontools versions.

That split is easy to forget later because both cases may surface during the
same troubleshooting session, but they need different remediation.

## Prediction Dependencies

SMART prediction depends on optional Python prediction dependencies. SMART
collection and HDSentinel monitoring are allowed to run even when that optional
prediction stack cannot load. This matters on older CPUs where the installed
NumPy package can fail during native-extension loading before the Drive Health
page has a chance to run a check.

The operator meaning is intentionally simple: `SMART prediction unavailable`
means no prediction probability can be calculated on this machine right now.
It is not a drive-health alert by itself, and SMART plus HDSentinel checks can
still run.

- If the native loader reports the known NumPy `X86_V2` CPU-baseline failure,
  the operator-facing message is: `SMART prediction is unavailable because this
  machine's CPU cannot run the installed NumPy package. SMART and HDSentinel
  checks can still run.`
- If another optional prediction dependency fails to load, the operator-facing
  message is: `SMART prediction is unavailable because the prediction
  dependencies could not be loaded. SMART and HDSentinel checks can still run.`
- The technical import failure is written to the application log once at warning
  level during service import. The web app should still start.
- Normal installation does not ask admins to compile NumPy from source, and the
  installer does not block older CPUs just because SMART prediction may degrade.

Scheduled Drive Health treats prediction unavailability as a successful degraded
check when the backup drive is mounted and SMART data is readable.

- The scheduled result has no probability, no prediction, and no prediction
  threshold because the model did not produce a value to compare.
- The scheduled output includes the prediction-unavailable warning so task
  history and journal logs explain why the check is degraded.
- Prediction unavailability by itself does not create a website alert and does
  not send an alert email.
- HDSentinel monitoring still runs according to the Drive Health settings.

Actual SMART read failures still fail the scheduled check unless the existing
smartctl-JSON unsupported path can report available HDSentinel data instead.
- A manual health check still displays readable SMART attributes and the current
  HDSentinel snapshot when prediction is unavailable. The prediction-unavailable
  text is a warning because the raw drive data was collected, but no telemetry
  row is appended unless a prediction label exists.

## Dashboard Summary

The Dashboard Drive Health tile reads only the latest summary stored in the running Flask process.
It does not read SMART data, run HDSentinel, or load any dashboard-specific health file during a
normal Dashboard refresh.

- On web app startup, the summary is `No check yet`.
- `GET /api/drive_health/summary` returns the RAM summary only.
- `POST /api/drive_health/refresh` runs a live SMART/HDSentinel probe, updates RAM, and returns the
  new summary.
- Timeout and unavailable-drive results stay neutral on the Dashboard because sleeping USB drives,
  docks, and adapters can need an explicit second check after spin-up.
- If SMART data is readable but prediction cannot run, Dashboard refresh succeeds
  and publishes a neutral summary with the prediction-unavailable detail and no
  failure probability. HDSentinel values may still be shown, but they do not turn
  the Dashboard health status into `good` or `warning`.
- The app does not persist Dashboard health summaries. Existing SMART telemetry and HDSentinel
  monitor state keep their own documented storage behavior.

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
- The NTFS driver selector controls the driver written to the managed `/etc/fstab` line and used by later manual mounts. `ntfs-3g` remains the compatibility default; `ntfs3` is available for newer kernels.
- A driver-only save is intentionally non-disruptive. The current live mount keeps its existing driver until the drive is unmounted and mounted again.
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
- If the mount point changes, also check `/etc/samba/simple_safer_server_shares.conf` (see [Network File Sharing](network_file_sharing.md)).
- Do not modify unrelated `/etc/fstab` entries.
- Back up `/etc/fstab` before editing it manually.

Important file locations:

- App config: `/etc/SimpleSaferServer/config.conf`
- Managed mount entry: `/etc/fstab`
- Samba main config: `/etc/samba/smb.conf` (includes SimpleSaferServer wiring)
- Managed share config: `/etc/samba/simple_safer_server_shares.conf`

Example managed `/etc/fstab` entry:

```fstab
UUID=2CD49023D48FED80    /media/backup    ntfs3    defaults,nofail    0    0 # SimpleSaferServer managed backup drive
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
