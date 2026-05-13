# Issue 005: Task Detail Disable Schedule Modal

Type: AFK

## Parent

PRD: Disable Scheduled Task Schedules

## What to build

Add the task detail user experience for Disable Schedule and Enable Schedule. The task detail toolbar should keep Start and Stop as service controls, add schedule controls for the timer, and use a stable modal for selecting disable duration with clear explanatory copy.

## Acceptance criteria

- [ ] Task detail shows Disable Schedule for every managed scheduled task.
- [ ] Task detail shows Enable Schedule when the schedule is disabled, externally disabled, or restore failed.
- [ ] Disable Schedule opens a modal instead of immediately disabling.
- [ ] The modal explains that automatic runs stop but manual Start still works.
- [ ] The modal offers 1 hour, 6 hours, 24 hours, 7 days, and Permanent choices.
- [ ] Selecting Permanent makes clear that the schedule stays disabled until manually enabled.
- [ ] The modal avoids dynamic skip-next-run warnings and avoids layout jumps.
- [ ] Confirming the modal calls the Disable Schedule API and updates schedule display.
- [ ] Enable Schedule runs immediately and shows success or error feedback.
- [ ] Tests or rendered-page assertions cover the controls, modal content, and state-dependent action visibility.

## Blocked by

- Issue 001: Disable and Enable Schedule Core Path
- Issue 002: Schedule State Display Contract
