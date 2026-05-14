# Issue 009: Task Toolbar Layout Stabilization & Premium Button Color Refresh

Type: AFK

## Parent

PRD: Disable Scheduled Task Schedules

## What to build

Stabilize the action bar layout on detailed task pages to completely eliminate horizontal DOM movement during background status polling updates. Separate manual service actions (**Start**, **Stop**) and timer schedule actions (**Disable Schedule**, **Enable Schedule**) into distinct visual button groups with a stable container gap. Ensure both schedule control buttons remain permanently present in the layout, setting native `disabled` properties on **Enable Schedule** when inapplicable rather than manipulating DOM classes. Replace indistinct secondary styling with rich, solid colors (`btn-warning` and `btn-primary`) to clearly signify interactive state.

## Acceptance criteria

- [ ] Detailed task toolbar organizes manual execution controls and scheduling controls into independent button groups.
- [ ] Action button groups maintain a stable container gap preventing visual crowding.
- [ ] Both Disable Schedule and Enable Schedule buttons are permanently rendered within the scheduling button group.
- [ ] When schedule enabling is inapplicable, Enable Schedule enters a `disabled` state natively without toggling `d-none`.
- [ ] Disable Schedule button is styled as `btn-warning` for strong visual affordance.
- [ ] Enable Schedule button is styled as `btn-primary` to attract attention to schedule resumption when applicable.
- [ ] Live status auto-polling cycles update button properties without causing horizontal toolbar shifting.

## Blocked by

- Issue 005: Task Detail Disable Schedule Modal
- Issue 006: Dashboard Row Display and Context Actions
