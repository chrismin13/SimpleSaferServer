# Dashboard

The Dashboard is the main interface for monitoring and managing the system. It provides an overview of system status, scheduled tasks, and system actions.

## Status Indicators
Four cards display real-time status:
- **Storage**: Shows drive connection status, used/total storage, and usage percentage.
- **Network File Sharing**: Shows if network file sharing is enabled (SMB status).
- **Hard Drive Health**: Shows the last drive-health summary remembered by the running web process.
  Dashboard load does not probe SMART or HDSentinel. Use the tile refresh button when you want a
  live drive-health probe. When both SMART failure risk and drive temperature are available, the
  tile shows them as a compact inline row so the overview does not jump taller during normal
  refreshes.
- **System Resources**: Displays CPU and RAM usage, and live network traffic (up/down rates).

## Task Schedule
- **Table**: Lists all scheduled tasks with columns for Task, Next Run, Last Run, Duration, Status, and Actions.
- **Actions**: Each task can be run immediately via the `Run Now` button.
- **Refresh**: Button to reload the task schedule.
- Scheduled task success follows the underlying command exit code. For DDNS, a provider-level error or missing provider configuration fails the `DDNS Update` task after the provider details are written for the DDNS page.
- `App Update` is the application self-update task. It runs the installed Git checkout's
  fast-forward update path and full installer, and is scheduled before the daily mount check. The
  task log includes update and installer output, and the log page keeps retrying if the web service
  briefly restarts during the install. The task detail page refreshes both the log and status badge
  while auto-refresh is enabled. Installer ANSI colors are rendered in the web log when the journal
  output includes them.

## System Actions
- **Unmount Storage**: Opens a modal to confirm a temporary unmount of the configured backup drive.
- Before unmounting, the app best-effort closes SMB sessions and stops the related background tasks so Samba does not keep the backup share busy.
- If the backup drive stays connected, SimpleSaferServer may remount it automatically during the next scheduled `Check Mount` run.
- When the next `Check Mount` run is available, the confirmation dialog explains the remount timing as a relative countdown so the user knows how long they have to remove or swap the drive.
- **Mount Storage**: Opens a modal to mount the storage drive.
- **Restart System**: Opens a modal to confirm and restart the system.
- **Shutdown System**: Opens a modal to confirm and shut down the system.
- Restart and shutdown are blocked while apt or dpkg is active so package operations are not interrupted.

## Modals
- **Unmount, Mount, Restart, Shutdown**: Each action temporarily disables its button and uses completion/error messaging.
- The unmount success message repeats that the dashboard action is temporary. That reminder matters because the app still manages the configured backup drive through its mount checks and `/etc/fstab` entry.

## Live Updates
- Status cards and system resources update live using background API calls.
- Drive Health uses RAM-only last-known state. After the web app restarts, the tile shows
  `No check yet` until a manual dashboard refresh or an in-process health check publishes a new
  summary. This avoids extra SD-card writes and avoids waking a sleeping backup drive on every
  dashboard load.
- Other operational status that can be rebuilt, such as DDNS provider status and System Updates
  operation state, uses volatile runtime storage rather than durable config storage.
- Task schedule and statuses are refreshed dynamically.

---

The Dashboard is the central hub for all system monitoring and management. 
