# Issue 007: Preserve Disabled Schedules During Unit Refresh

Type: AFK

## Parent

PRD: Disable Scheduled Task Schedules

## What to build

Ensure generated systemd unit refreshes, app updates, setup completion, and install paths preserve active SimpleSaferServer disabled schedules. Regenerating service and timer units should not silently re-enable a timer that the admin disabled through SimpleSaferServer.

## Acceptance criteria

- [ ] Generated unit refresh installs or refreshes the global restore service and timer.
- [ ] The global restore timer is enabled during normal install/setup.
- [ ] Main recurring task timers still remain inactive before setup completion as they do today.
- [ ] Active SimpleSaferServer temporary disables remain disabled after unit regeneration.
- [ ] Active SimpleSaferServer permanent disables remain disabled after unit regeneration.
- [ ] Timers without active SimpleSaferServer disable records are enabled according to existing activation rules.
- [ ] App update paths that refresh units preserve active disabled schedule state.
- [ ] Tests cover activation enabled, activation disabled before setup completion, and preservation of disabled-timer state during refresh.

## Blocked by

- Issue 001: Disable and Enable Schedule Core Path
- Issue 003: Five-Minute Restore Helper and Retry Policy
