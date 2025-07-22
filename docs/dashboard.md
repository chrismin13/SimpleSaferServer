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

## System Actions
- **Unmount Storage**: Opens a modal to confirm and unmount the storage drive.
- **Mount Storage**: Opens a modal to mount the storage drive.
- **Restart System**: Opens a modal to confirm and restart the system.
- **Shutdown System**: Opens a modal to confirm and shut down the system.

## Modals
- **Unmount, Mount, Restart, Shutdown**: Each action has a confirmation modal with status, spinner, and feedback.

## Live Updates
- Status cards and system resources update live using background API calls.
- Task schedule and statuses are refreshed dynamically.

---

The Dashboard is the central hub for all system monitoring and management. 