# Dashboard

The Dashboard is the main interface for monitoring and managing the system. It provides an overview of system status, scheduled tasks, and system actions.

## Status Indicators
Four cards display real-time status:
- **Storage**: Shows drive connection status, used/total storage, and usage percentage.
- **Network File Sharing**: Shows if network file sharing is enabled (SMB status).
- **Hard Drive Health**: Shows drive health status, failure risk, and temperature.
- **System Resources**: Displays CPU and RAM usage, and live network traffic (up/down rates).

## Task Schedule
- **Table**: Lists all scheduled tasks with columns for Task, Next Run, Last Run, Duration, Status, and Actions.
- **Actions**: Each task can be run immediately via the `Run Now` button.
- **Refresh**: Button to reload the task schedule.
- Scheduled task success follows the underlying command exit code. For DDNS, a provider-level error or missing provider configuration fails the `DDNS Update` task after the provider details are written for the DDNS page.

## System Actions
- **Unmount Storage**: Opens a modal to confirm a temporary unmount of the configured backup drive.
- Before unmounting, the app best-effort closes SMB sessions and stops the related background tasks so Samba does not keep the backup share busy.
- If the backup drive stays connected, SimpleSaferServer may remount it automatically during the next scheduled `Check Mount` run.
- When the next `Check Mount` run is available, the confirmation dialog explains the remount timing as a relative countdown so the user knows how long they have to remove or swap the drive.
- **Mount Storage**: Opens a modal to mount the storage drive.
- **Restart System**: Opens a modal to confirm and restart the system.
- **Shutdown System**: Opens a modal to confirm and shut down the system.

## Modals
- **Unmount, Mount, Restart, Shutdown**: Each action temporarily disables its button and uses completion/error messaging.
- The unmount success message repeats that the dashboard action is temporary. That reminder matters because the app still manages the configured backup drive through its mount checks and `/etc/fstab` entry.

## Live Updates
- Status cards and system resources update live using background API calls.
- Task schedule and statuses are refreshed dynamically.

---

The Dashboard is the central hub for all system monitoring and management. 
