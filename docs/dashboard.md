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
- **Table**: Lists all scheduled tasks with columns for Task, Status, Last Run, and Next Run.
- **Next Run**: Shows the active next run time or a short schedule state label. Temporary disables
  show `Disabled until 18:00`, `Disabled until Tomorrow 18:00`, or a later date such as
  `Disabled until May 16 18:00`. Permanent disables show `Disabled`. Timers disabled outside
  SimpleSaferServer show `Disabled externally`; unexpected timer states show `Schedule issue`.
  Disabled schedule labels are danger-colored in this field only, so automatic-run suspension stands
  out without making the entire task row look failed. Schedule issues remain warning-colored because
  they mean the timer state needs investigation.
- **Task Schedule Control**: Right-click a task row to Start, Stop, Disable Schedule, or Enable
  Schedule when that action applies. The menu stays open across passive schedule refreshes so the
  operator does not lose the selected row actions while reading the menu.
- **Disable Schedule**: Disables the task's systemd timer, not the service. Automatic runs stop, but manual Start remains available. The shared dialog supports preset durations, permanent disable, and a custom positive
  whole-hour duration.
- Scheduled task success follows the underlying command exit code. For DDNS, a provider-level error or missing provider configuration fails the `DDNS Update` task after the provider details are written for the DDNS page.
- `App Update` is the application self-update task. It runs the installed Git checkout's
  fast-forward update path and full installer, and is scheduled before the daily mount check. The
  task log includes update and installer output, and the log page keeps retrying if the web service
  briefly restarts during the install. The task detail page refreshes both the log and status badge
  while auto-refresh is enabled, showing up to the latest 500 journal lines. Installer ANSI colors
  are rendered in the web log when the journal output includes them.

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
- When SMART data is readable but prediction cannot run, the refresh still succeeds. The tile keeps
  a neutral health status, shows the prediction-unavailable detail, and omits failure probability
  instead of deriving a pass/fail status from HDSentinel alone.
- Other operational status that can be rebuilt, such as DDNS provider status and System Updates
  operation state, uses volatile runtime storage rather than durable config storage.
- Task schedule and statuses are refreshed dynamically.

---

The Dashboard is the central hub for all system monitoring and management. 
