# Drive Health

The Drive Health page combines two views of the configured backup drive:

- SMART data plus the local machine-learning failure prediction
- HDSentinel health and performance reporting

## Features
- **Run Health Check**: Runs a manual SMART and HDSentinel refresh from the page.
- **Prediction Result**: Shows whether the SMART model predicts failure, with probability percentage.
- **Missing Attributes**: Lists SMART attributes that fell back to defaults.
- **HDSentinel Status**: Shows install state, device, model, serial, health, performance, temperature, size, and last checked time.
- **HDSentinel Settings**: Lets users enable or disable HDSentinel monitoring and toggle health-change alerts.
- **SMART Data Table**: Lists SMART attributes, descriptions, raw values, and status.
- **Download Telemetry**: Downloads the SMART telemetry CSV.

## Alerting
- HDSentinel alerts only trigger on health changes between scheduled checks.
- Temperature is displayed but does not currently trigger alerts.

## Re-running Backup Drive Setup
- Use the advanced section on the Drive Health page only if the backup drive changed or the original identifiers were detected incorrectly.
- The flow is designed to re-run the backup drive mount setup safely instead of editing UUID or USB ID fields directly.
- It updates only the SimpleSaferServer-managed backup mount entry in `/etc/fstab`.
- The rerun flow always refreshes the managed entry with the boot-safe `defaults,nofail` mount options.
- If the app finds multiple managed entries or a conflicting non-SimpleSaferServer entry using the same UUID or mount point, it stops and asks for manual cleanup.

What "SimpleSaferServer-managed" means:
- It refers to the backup drive line in `/etc/fstab` that ends with the marker comment `# SimpleSaferServer managed backup drive`.
- The app does not treat unrelated `/etc/fstab` lines as its own unless they carry that backup-drive marker (or the older legacy marker).

## Manual Recovery
If you need to inspect or repair the backup drive configuration manually, start here:

```bash
sudo awk '1' /etc/SimpleSaferServer/config.conf
sudo grep -n 'SimpleSaferServer' /etc/fstab
```

Useful commands:

```bash
lsblk -f
sudo blkid -s UUID -o value /dev/sdX1
lsusb
sudo findmnt --verify
```

Manual recovery rules:
- Update `/etc/SimpleSaferServer/config.conf` only if you know the correct `mount_point`, `uuid`, and `usb_id` values.
- Update only the SimpleSaferServer-managed line in `/etc/fstab`.
- If the mount point changes, also check the backup share path in `/etc/samba/smb.conf`.
- Do not modify unrelated `/etc/fstab` entries.
- Create a backup of `/etc/fstab` before editing it.

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

---

This page is the main place to inspect the backup drive's current SMART and HDSentinel health data.
