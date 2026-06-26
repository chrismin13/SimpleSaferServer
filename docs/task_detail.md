# Task Detail

The Task Detail page shows information and logs for a background task.

## Task Information
- **Task Name**: Displayed at the top.
- **Status**: Shows current status with a badge (Success, Failure, Running, Missing, Not Run Yet, Error).
- **Schedule**: Shows the worker-owned schedule state with a badge. Schedule issues use a warning
  badge, and active schedules use the normal calendar badge.

## Controls
- **Start**: Button to start the task (confirmation required). The task only starts after its
  module has been applied.
- **Stop**: Button to stop the task (confirmation required).
- **Auto Refresh**: Toggle to enable/disable auto-refresh of logs.

Automatic task timing is owned by the SimpleSaferServer worker. Change the feature setting that owns
the job instead of disabling a systemd timer.

## Logs
- **Recent Logs**: Shows the latest worker job result in a preformatted area.

## Navigation
- **Back to Dashboard**: Button to return to the main dashboard.

---

This page provides detailed information and control for each background task.
