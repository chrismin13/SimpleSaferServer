# Issue 008: Documentation and Uninstall Cleanup

Type: AFK

## Parent

PRD: Disable Scheduled Task Schedules

## What to build

Document the Disable Schedule and Enable Schedule behavior and make uninstall clean up any new installed artifacts and durable state. Documentation should explain that disabling a schedule disables the systemd timer, not the service, and that manual Start remains available.

## Acceptance criteria

- [ ] Dashboard documentation describes schedule labels in the Next Run field.
- [ ] Task detail documentation describes Disable Schedule, Enable Schedule, duration choices, permanent disable, and manual Start behavior.
- [ ] System update or install documentation notes that active SimpleSaferServer disabled schedules are preserved during unit regeneration.
- [ ] Fake mode documentation covers simulated disabled schedule behavior if relevant.
- [ ] Uninstall removes the global restore service and timer.
- [ ] Uninstall removes the restore helper script if one is installed.
- [ ] Uninstall removes disabled-timer state when app data is removed.
- [ ] Public documentation links are checked for related dashboard/task detail docs.
- [ ] No README changes are made.
- [ ] Tests cover uninstall cleanup for new units and state where existing uninstall tests provide prior art.

## Blocked by

- Issue 003: Five-Minute Restore Helper and Retry Policy
- Issue 006: Dashboard Row Display and Context Actions
- Issue 007: Preserve Disabled Schedules During Unit Refresh
