# Setup Wizard

The Setup Wizard guides you through the initial configuration of your backup system. It consists of six main steps, each with its own section and options.

## Navigation and Progress
- **Progress Bar**: Shows current step and allows navigation between steps.
- **Validation**: Inline feedback for all fields.
- **Spinners**: Buttons show spinners during processing.

## Step 1: Create Admin Account
- **Username**: Enter a username (3-32 characters, letters, numbers, underscores, hyphens).
- **Server Name**: Name your server (required).
- **Password**: Enter a password (minimum 4 characters).
- **Confirm Password**: Re-enter the password to confirm.
- **Validation**: Inline feedback is provided for all fields.
- **Button**: `Create Admin Account` (proceeds to next step on success).

## Step 2: Drive Format (Optional)
- **Drive Selection**: Choose a drive to format from a dropdown (shows model, size, type, and mount status).
- **Unmount Drive**: Button to unmount the selected drive (required before formatting).
- **Format Drive**: Button to format the selected drive (erases all data).
- **Status Area**: Shows messages about formatting/unmounting.
- **Warning**: Formatting erases all data on the drive.
- **Skip Formatting**: Button to proceed without formatting.

## Step 3: Drive Mount
- **Drive Selection**: Choose an NTFS partition to mount.
- **Advanced Options**: Toggle to show mount point and auto-mount at boot.
- **Mount Point**: Set the mount directory (default: `/media/backup`).
- **Auto Mount**: Checkbox to mount automatically at boot.
- **Unmount/Mount Buttons**: Unmount or mount the selected drive.
- **Status/Error Areas**: Inline feedback for actions.

## Step 4: Backup Configuration
- **Backup Mode**: Choose between:
  - Easy MEGA Cloud Backup
  - Advanced (Paste rclone config)

### MEGA Easy Mode
- **MEGA Email/Password**: Enter MEGA credentials.
- **Connect & Choose Folder**: Button to connect and select a MEGA folder.
- **Folder Path**: Shows selected MEGA folder.
- **Modal**: MEGA folder picker modal for cloud backup setup.
- **Warning**: All files in the selected MEGA folder will be overwritten during backup.

### Advanced rclone Config
- **Rclone Configuration**: Paste rclone config.
- **Remote Name and Path**: Enter in the format `remotename:/path`.
- **Warning**: rclone will synchronize the remote path to match the local backup directory.

- **Save Backup Configuration**: Button to save settings.

## Step 5: Email Setup
- **Email Address**: Enter the address for alerts.
- **From Address**: Enter the address that will appear in the From field of alert emails. This must be a valid, verified sender for your SMTP service (e.g., the authenticated SMTP user or a domain-verified address). Some SMTP providers will only deliver mail if the From address matches the authenticated user or a verified sender.
- **SMTP Configuration**: Enter SMTP server, port, username, and password.
- **Save Email Configuration**: Button to save settings.

## Step 6: Schedule
- **Backup Time**: Set the daily backup time.
- **Bandwidth Limit**: (Optional) Limit backup bandwidth (e.g., 4M for 4 MB/s).
- **Save Schedule**: Button to save and complete setup.


---

After completing all steps, the system is ready for use and redirects to the main interface. 