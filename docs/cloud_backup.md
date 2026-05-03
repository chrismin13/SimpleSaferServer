# Cloud Backup

The Cloud Backup page manages cloud backup settings, schedules, and status.

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
