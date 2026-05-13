# Issue 006: Dashboard Row Display and Context Actions

Type: AFK

## Parent

PRD: Disable Scheduled Task Schedules

## What to build

Update the dashboard scheduled task table and right-click task menu to display and control schedule state without widening the table. The Next Run field should show the schedule label, and the row context menu should include the same task actions as task detail where applicable.

## Acceptance criteria

- [ ] Dashboard task rows display schedule labels in the existing Next Run field.
- [ ] The dashboard table does not add a new schedule column.
- [ ] Active next runs, temporary disabled schedules, permanent disabled schedules, external disables, restore failures, and schedule issues render with the agreed short labels.
- [ ] Right-click task menu includes Start, Stop, Disable Schedule, and Enable Schedule where applicable.
- [ ] Disable Schedule from the right-click menu opens the same modal flow as task detail.
- [ ] Enable Schedule from the right-click menu runs immediately and shows success or error feedback.
- [ ] Mobile table behavior remains compact and readable.
- [ ] Tests or rendered-page assertions cover labels, no added column, and context action availability.

## Blocked by

- Issue 002: Schedule State Display Contract
- Issue 005: Task Detail Disable Schedule Modal
