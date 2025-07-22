# Cloud Backup

The Cloud Backup page manages cloud backup settings, schedules, and status.

## Status Card
- **Cloud Backup Status**: Shows current status, last backup, next scheduled backup, and duration.
- **View Log**: Link to the backup task log.
- **Run Backup Now**: Button to start a backup immediately (shows spinner while running).
- **Error Feedback**: Inline error messages for backup issues.

## Backup Schedule & Bandwidth
- **Backup Time**: Set the daily backup time.
- **Bandwidth Limit**: (Optional) Limit backup bandwidth (e.g., 4M for 4 MB/s).
- **Save**: Button to save schedule settings (shows spinner while saving).
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
- **Rclone Configuration**: Paste rclone config.
- **Remote Name and Path**: Enter in the format `remotename:/path`.
- **Warning**: rclone will synchronize the remote path to match the local backup directory.

- **Save**: Button to save backup configuration (shows spinner while saving).
- **Error/Success Feedback**: Inline messages for save actions.

## Modal
- **MEGA Folder Picker**: Modal dialog to select a folder in MEGA.

---

This page allows you to configure and monitor cloud backups for your system. 