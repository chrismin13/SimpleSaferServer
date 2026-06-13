# Drive Health

The Drive Health page is the main place to inspect disk health.

It combines:

- SMART attribute collection and raw attribute display
- HDSentinel health, performance, temperature, and device reporting

## Features

- Run a manual health refresh from the page.
- Refresh the Dashboard Drive Health tile explicitly when you want a live probe from the overview.
- View SMART attributes returned by `smartctl` JSON output.
- View missing SMART attributes that fell back to documented defaults.
- View the HDSentinel device snapshot returned by an explicit manual refresh.
- View the HDSentinel drive list returned by an explicit manual refresh.
- Enable or disable HDSentinel monitoring and change alert settings.

## SMART Error Reporting

SMART collection uses `smartctl` JSON output when the installed `smartctl` version supports `-j`.

- The "upgrade smartmontools" warning is reserved for the explicit case where `smartctl -h` shows that JSON output is unavailable.
- If `smartctl` advertises JSON support but the actual SMART read still fails, the app preserves the original `smartctl` error instead. This matters because USB bridges, controller quirks, and device read failures can all break SMART collection even on newer smartmontools versions.

That split is easy to forget later because both cases may surface during the same troubleshooting session, but they need different remediation.

## HDSentinel Monitoring And Alerts

HDSentinel is the source for the simple health meter shown on the Dashboard after a manual Dashboard refresh or Drive Health page refresh actually runs in the web app process.

- Health `50%` and above is shown as healthy.
- Health below `50%` is shown as a warning.
- Health below `25%` is shown as critical.
- If HDSentinel is disabled, unavailable, or has not run yet, the Dashboard status remains unknown.

Scheduled Drive Health keeps durable HDSentinel state at `/var/lib/SimpleSaferServer/hdsentinel_state.json` in real mode. On each scheduled check it compares the previous successful health percentage with the current successful health percentage for each detected drive. Normal Drive Health page loads do not read that state as live dashboard health; the file exists for scheduled change detection.

When HDSentinel monitoring and health-change alerts are enabled, any health percentage change creates a HDSentinel alert for the drive that changed. The alert does not use the Dashboard warning/critical thresholds; it is deliberately based on change detection so operators see drive-health movement even when the absolute value is still high.

## Dashboard Summary

The Dashboard Drive Health tile reads only the latest summary stored in the running Flask process. It does not read SMART data, run HDSentinel, read scheduled HDSentinel state, or load a dashboard-specific health file during a normal Dashboard refresh.

- On web app startup, the summary is `No check yet`.
- `GET /api/drive_health/summary` returns the RAM summary only.
- `POST /api/drive_health/refresh` runs a live SMART/HDSentinel probe, updates RAM, and returns the new summary.
- Timeout and unavailable-drive results stay neutral on the Dashboard unless HDSentinel returns a usable health percentage.
- The app does not persist Dashboard health summaries. HDSentinel monitor state keeps its own documented storage behavior for scheduled health-change alerts.

## Scheduled Checks

Scheduled Drive Health tries to use HDSentinel's full drive list when it is available. This lets the app monitor more than one disk instead of tying health only to the configured storage path. The Drive Health table marks the prepared SimpleSaferServer storage drive when it can match the detected device safely.

Scheduled Drive Health still treats general SMART read failures as task failures because those failures can signal real device, bridge, or permission problems.

The one degraded-success exception is the existing smartctl JSON unsupported path: if SMART cannot run only because the installed smartctl lacks JSON output and HDSentinel reports a usable health percentage, the scheduled check can still complete with the HDSentinel snapshot.

## Storage Setup

Storage setup has moved to the Storage page.

Use Storage when:

- the storage folder changes
- a prepared drive is replaced
- an existing folder should be used instead of a prepared drive
- the cloud-backup storage marker needs to be repaired

Drive Health does not decide where backups are stored. It checks drive health and reports what the local tools can read.

## What "SimpleSaferServer-managed" Means

The app only manages the `/etc/fstab` line for the backup drive that ends with:

```text
# SimpleSaferServer managed backup drive
```

The app does not treat unrelated `/etc/fstab` lines as its own unless they use that marker or the older legacy marker.

## Safety Rules

- The rerun flow does not edit unrelated `/etc/fstab` entries.
- If the app finds multiple managed entries, it stops and asks for manual cleanup.
- If `ntfs3` is selected on a kernel that cannot mount `ntfs3`, the configure step fails and restores the previous managed `/etc/fstab` entry.
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
- Use `ntfs-3g` or `ntfs3` as the filesystem type for the managed backup-drive line.
- Run `sudo systemctl daemon-reload` after manually changing `/etc/fstab` so systemd forgets the old generated mount unit state.
- If the mount point changes, use the Storage page so the app can update the storage marker and the default network share. See [Network File Sharing](network_file_sharing.md) if you need to inspect the managed share file manually.
- Do not modify unrelated `/etc/fstab` entries.
- Back up `/etc/fstab` before editing it manually.

Important file locations:

- App config: `/etc/SimpleSaferServer/config.conf`
- Managed mount entry: `/etc/fstab`
- Samba main config: `/etc/samba/smb.conf` (includes SimpleSaferServer wiring)
- Managed share config: `/etc/samba/simple_safer_server_shares.conf`

Example managed `/etc/fstab` entry:

```fstab
UUID=2CD49023D48FED80    /media/backup    ntfs-3g    defaults,nofail                                 0    0 # SimpleSaferServer managed backup drive
# or, when the kernel NTFS driver is deliberately selected:
UUID=2CD49023D48FED80    /media/backup    ntfs3       rw,uid=0,gid=0,dmask=000,fmask=000,nofail    0    0 # SimpleSaferServer managed backup drive
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
