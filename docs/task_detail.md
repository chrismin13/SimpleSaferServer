# Task Detail

The Task Detail page shows information and logs for a specific scheduled task.

## Task Information
- **Task Name**: Displayed at the top.
- **Status**: Shows current status with a badge (Success, Failure, Running, Missing, Not Run Yet, Error).
- **Schedule**: Shows the Task Schedule state with a badge. Disabled schedule states use a
  danger-colored disabled-calendar badge, schedule issues use a warning badge, and active schedules
  use the normal calendar badge.
- **About this task**: Explains what the task does, which systemd service it starts, and which
  systemd timer controls automatic runs.

## Built-In Tasks

- **Check Mount**: Makes sure the configured backup drive is mounted before backup work starts. Setup schedules it shortly before the daily Cloud Backup time.
- **Drive Health Check**: Checks the configured backup drive with SMART and HDSentinel. Setup schedules it after Check Mount and before Cloud Backup.
- **Cloud Backup**: Syncs the local backup folder to the configured MEGA or rclone destination. It runs daily at the Backup Time saved in Setup or on the Cloud Backup page.
- **DDNS Update**: Updates enabled DuckDNS or Cloudflare DNS records with the current public IPv4 address. It runs on its DDNS systemd timer and can also be forced from the DDNS page.
- **App Update**: Updates the installed SimpleSaferServer checkout and reruns the installer refresh path. It runs on its app-update systemd timer before the daily backup maintenance window.

Manual **Start** runs the task's systemd service immediately. **Manage Schedule** controls the matching systemd timer, which is what automatic runs use.

## Controls
- **Start**: Button to start the task (confirmation required).
- **Stop**: Button to stop the task (confirmation required).
- **Disable Schedule**: Opens a modal for disabling automatic runs for 1 hour, 6 hours, 24 hours,
  7 days, or permanently. This disables the systemd `.timer` only; manual Start still starts the
  `.service`.
- **Enable Schedule**: Re-enables the timer immediately. It is available for SimpleSaferServer
  disables, externally disabled timers, restore failures, and schedule issues where retrying timer
  enablement is useful.
- **Permanent Disable**: Leaves automatic runs off until Enable Schedule is used.
- **Auto Refresh**: Toggle to enable/disable auto-refresh of logs.

If the schedule is in an unexpected systemd state, the page shows the raw timer state and points the
admin toward checking systemd or regenerating units through System Updates.

## Logs
- **Recent Logs**: Shows the latest 500 journal lines for the task in a preformatted area.
  Auto-refresh reloads the same 500-line window so long-running task output, including application
  update installer output, stays visible without each page path choosing its own log length.

## Navigation
- **Back to Dashboard**: Button to return to the main dashboard.

---

This page provides detailed information and control for each scheduled task.
