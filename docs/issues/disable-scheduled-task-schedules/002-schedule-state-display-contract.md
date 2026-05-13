# Issue 002: Schedule State Display Contract

Type: AFK

## Parent

PRD: Disable Scheduled Task Schedules

## What to build

Expose a stable schedule-state contract that lets the dashboard and task detail display the schedule accurately without parsing raw systemd output. The contract should distinguish SimpleSaferServer-managed disables, externally disabled timers, restore-failed timers, active schedules, and unexpected schedule issues.

This slice should keep the dashboard compact by using the existing Next Run field for schedule labels rather than adding a new column.

## Acceptance criteria

- [ ] Task summaries include a structured schedule object with a display label and machine-readable state.
- [ ] Active schedules display compact next-run labels for today, tomorrow, and later dates.
- [ ] SimpleSaferServer temporary disables display labels like `Disabled until 18:00`, `Disabled until Tomorrow 18:00`, and `Disabled until May 16 18:00`.
- [ ] SimpleSaferServer permanent disables display `Disabled`.
- [ ] Timers disabled in systemd without SimpleSaferServer state display `Disabled externally`.
- [ ] Unexpected systemd timer states display `Schedule issue`.
- [ ] Task detail exposes raw systemd state for schedule issues and gives concise repair guidance.
- [ ] The dashboard does not add a schedule column.
- [ ] Tests cover label formatting and state selection without asserting private helper implementation.

## Blocked by

- Issue 001: Disable and Enable Schedule Core Path
