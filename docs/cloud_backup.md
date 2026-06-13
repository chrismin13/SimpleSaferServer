# Cloud Backup

The Cloud Backup page manages cloud backup settings, schedules, and status.

Cloud Backup uses `rclone sync`. A sync makes the remote folder match the local storage folder. That means a missing local file can be deleted from the cloud destination. This is useful when the local storage is healthy, but it is dangerous if the local storage folder is empty because a disk, pool, or folder mount failed.

SimpleSaferServer therefore checks the configured storage location before every cloud backup. If the storage checks fail, the backup does not run.

## Status Card
- **Cloud Backup Status**: Shows current status, last backup, next scheduled backup, and duration.
- **View Log**: Link to the backup task log.
- **Run Backup Now**: Button to start a backup immediately by disabling during the request.
- **Error Feedback**: Inline error messages for backup issues.

## Backup Schedule & Bandwidth
- **Backup Time**: Set the daily backup time in two-digit 24-hour `HH:MM` format.
- **Bandwidth Limit**: (Optional) Limit backup bandwidth (e.g., 4M for 4 MB/s).
- **Save**: Button to save schedule settings by disabling during the request.
- **Error/Success Feedback**: Inline messages for save actions.

## Cloud Backup Settings
- **Backup Mode**: Choose between:
  - MEGA (Simple)
  - Advanced (Paste rclone config)
- **Disabled**: Cloud Backup can be skipped during setup. When it is disabled, the timer is not enabled and manual backup runs are blocked until Cloud Backup is configured.

### MEGA Simple Mode
- **MEGA Email/Password**: Enter MEGA credentials (fields may be disabled if already saved).
- **Save/Change Credentials**: Buttons to manage MEGA credentials.
- **Backup Folder in MEGA**: Select or browse for the backup folder.
- **Warning**: All files in the selected MEGA folder will be overwritten during backup.

### Advanced rclone Config
- **Rclone Configuration**: Paste or edit the stored rclone config. Administrators can inspect this
  value because this page is the editor for cloud-backup credentials and destinations.
- **Remote Name and Path**: Enter in the format `remotename:/path`.
- **Warning**: rclone will synchronize the remote path to match the local backup directory.

## Storage Safety Checks

Before a scheduled or manual cloud backup starts, SimpleSaferServer checks the configured storage location.

The check confirms:

- the configured storage path exists
- the `.simple-safer-server/storage.json` marker file exists
- the marker file contains the storage ID saved in the app config
- the marker file can be read
- the storage folder can be written to
- the test file written by the app can be read back
- the test file can be deleted

For a drive prepared by SimpleSaferServer, the check also confirms that the app-managed mount point is mounted. For an existing folder, the app does not mount it, but it records where that folder was mounted when it was selected. If the folder later appears under a different mount source, the backup fails until an administrator checks it.

These checks are deliberately cautious. The safest failure is to skip a backup and alert the administrator. The unsafe failure would be syncing an empty or wrong folder to the cloud and deleting good remote files.

If the marker file is deleted, SimpleSaferServer treats that as unsafe and blocks Cloud Backup. Use the Storage page to repair the marker after confirming the folder is the correct storage location.

## Fake Mode

Fake mode avoids local system changes, but cloud-backup provider calls can still run when real
credentials and destinations are configured. Use a test destination when developing against a real
provider from fake mode.

- **Save**: Button to save backup configuration by disabling during the request.
- **Error/Success Feedback**: Inline messages for save actions.

## Modal
- **MEGA Folder Picker**: Modal dialog to select a folder in MEGA.

---

This page allows you to configure and monitor cloud backups for your system. 
