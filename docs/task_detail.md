# Task Detail

The Task Detail page shows information and logs for a specific scheduled task.

## Task Information
- **Task Name**: Displayed at the top.
- **Status**: Shows current status with a badge (Success, Failure, Running, Missing, Not Run Yet, Error).

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
