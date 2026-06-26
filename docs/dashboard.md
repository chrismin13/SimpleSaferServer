# Dashboard

The Dashboard is the main interface for monitoring and managing the system. It provides an overview of system status, scheduled tasks, and system actions.

## Status Indicators
Four cards display real-time status:
- **Storage**: Shows passive storage status, plus used/total storage and usage percentage when that information can be read. The Dashboard does not read the storage marker or write a test file during page load, because that can wake a sleeping backup drive.
- **Network File Sharing**: Summarizes `smbd`, `nmbd`, and `wsdd2`. The tile is operational when
  `smbd` is active and discovery services are either active or unavailable (not installed), partial
  when `smbd` is active but at least one discovery service is inactive, and down
  when `smbd` is not active.
- **Hard Drive Health**: Shows the last drive-health summary remembered by the running web process.
  Dashboard load does not probe SMART or HDSentinel. Use the tile refresh button when you want a
  live drive-health probe. The compact status is based on HDSentinel's health percentage when it is
  available; SMART remains a detailed inspection surface on the Drive Health page.
- **System Resources**: Displays CPU and RAM usage, and live network traffic (up/down rates).

## Backup Protection Checklist
The app has one shared 3-2-1 backup-readiness checklist for setup and dashboard UI. The dashboard
renders it from the shared partial and can refresh it through the htmx fragment
`GET /fragments/backup-readiness`. JSON clients can read the same checklist data from
`GET /api/backup-readiness`. It checks:

- storage has been chosen and has a storage marker
- the managed `backup` network share exists
- cloud backup is configured
- SMTP alerts are configured
- a backup schedule has been chosen

Each item reports `complete`, `incomplete`, or `skipped`. Skipping cloud backup lets setup continue,
but the dashboard should still show that backup protection is incomplete until an off-site copy is
configured.

## Task Schedule
- **Table**: Lists background tasks with columns for Task, Status, Last Run, and Next Run.
- **Next Run**: Shows the next worker run time or a short worker state label. Schedule issues remain
  warning-colored because they mean the worker schedule state needs investigation.
- **Task Actions**: Right-click a task row to Start or Stop the task when that action applies. The
  menu stays open across passive schedule refreshes so the operator does not lose the selected row
  actions while reading the menu.
- Scheduled task success follows the underlying command exit code. For DDNS, a provider-level error or missing provider configuration fails the `DDNS Update` task after the provider details are written for the DDNS page.
- Application self-updates are shown on the System Updates page as unavailable until SSS has a
  release archive or package updater.

## System Actions
- **Unmount Storage**: Opens a modal to confirm a temporary unmount of the configured backup drive. This action is available only when SimpleSaferServer manages the backup drive.
- Before unmounting, the app best-effort closes SMB sessions and stops the related background tasks so Samba does not keep the backup share busy.
- If the backup drive stays connected, SimpleSaferServer may remount it automatically during the next scheduled `Check Mount` run.
- When the next `Check Mount` run is available, the confirmation dialog explains the remount timing as a relative countdown so the user knows how long they have to remove or swap the drive.
- **Mount Storage**: Opens a modal to mount the storage drive. When a SimpleSaferServer-managed `/etc/fstab` entry exists for the mount point, the app verifies that the entry's `UUID=` still matches the configured backup drive before using it for the remount.
- **Storage Settings**: Opens the Storage page when the configured storage is an existing folder. SimpleSaferServer does not mount or unmount existing-folder storage because that folder is managed outside the app.
- **Restart System**: Opens a modal to confirm and restart the system.
- **Shutdown System**: Opens a modal to confirm and shut down the system.
- Restart and shutdown are blocked while apt or dpkg is active so package operations are not interrupted.

## Modals
- **Unmount, Mount, Restart, Shutdown**: Each action temporarily disables its button and uses completion/error messaging.
- The unmount success message repeats that the dashboard action is temporary. That reminder matters because the app still manages the configured backup drive through its mount checks and `/etc/fstab` entry.

## Live Updates
- Status cards and system resources update live using background API calls.
- Storage live updates stay passive. They may read disk-usage statistics, but they do not run the cloud-backup marker check or the read-write probe. Use **Run safety check** on the Storage page when you want the full check.
- Drive Health uses RAM-only last-known state. After the web app restarts, the tile shows
  `No check yet` until a manual dashboard refresh or an in-process health check publishes a new
  summary. This avoids extra SD-card writes and avoids waking a sleeping backup drive on every
  dashboard load.
- When HDSentinel returns a health percentage, the tile uses that percentage for the compact status:
  `50%` and above is healthy, below `50%` is warning, and below `25%` is critical. If HDSentinel is
  unavailable, disabled, or has not run yet, the compact status stays neutral.
- Other operational status that can be rebuilt, such as DDNS provider status and System Updates
  operation state, uses volatile runtime storage rather than durable config storage.
- Task schedule and statuses are refreshed dynamically.

---

The Dashboard is the central hub for all system monitoring and management. 
