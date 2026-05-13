# Issue 001: Disable and Enable Schedule Core Path

Type: AFK

## Parent

PRD: Disable Scheduled Task Schedules

## What to build

Build the smallest end-to-end Disable Schedule and Enable Schedule path for managed scheduled tasks. An admin can disable a task's automatic schedule through the task API, SimpleSaferServer disables the systemd timer without disabling the service, durable state records the SimpleSaferServer-managed disable, and Enable Schedule restores normal timer scheduling.

This slice should include fake-mode behavior and structured schedule state in task summaries, but it does not need the five-minute restore helper or full dashboard modal yet.

## Acceptance criteria

- [ ] Disable Schedule runs the systemd timer disable operation for the task timer and does not disable the task service.
- [ ] SimpleSaferServer writes durable disabled-timer state only after the systemd disable operation succeeds.
- [ ] Enable Schedule runs the systemd timer enable operation and removes any SimpleSaferServer disabled-timer state for that task.
- [ ] Manual task Start remains available and still starts the service while the schedule is disabled.
- [ ] A repeated Disable Schedule action replaces the existing SimpleSaferServer disabled state for that timer.
- [ ] Temporary and permanent disable modes are represented in durable state.
- [ ] Fake mode simulates disable and enable without invoking systemd.
- [ ] Task summaries include structured schedule state for active, temporary disabled, permanent disabled, and fake-mode disabled schedules.
- [ ] Focused tests cover successful disable, failed disable with no state write, enable, replacement, and fake-mode behavior.

## Blocked by

None - can start immediately
