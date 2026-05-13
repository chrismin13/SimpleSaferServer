# Issue 004: Restore Failure Alert Notifications

Type: AFK

## Parent

PRD: Disable Scheduled Task Schedules

## What to build

Route restore failure notifications through the existing alert and email behavior. When a temporary schedule restore fails three times, SimpleSaferServer records a normal app alert and sends email using configured alert notification settings. Normal Disable Schedule and Enable Schedule actions do not alert.

This slice should extract or introduce a shared alert-and-email helper so restore failures do not duplicate SMTP and alert-store behavior.

## Acceptance criteria

- [ ] Restore failure after three attempts creates a normal app alert with useful task and timer context.
- [ ] Restore failure sends email when existing email settings are complete.
- [ ] Restore failure does not send email in fake mode.
- [ ] Normal Disable Schedule actions do not create alerts or send email.
- [ ] Normal Enable Schedule actions do not create alerts or send email.
- [ ] The restore helper uses shared alert notification behavior rather than Flask routes or direct duplicated SMTP parsing.
- [ ] Existing alert behavior remains compatible with current alert pages and alert store tests.
- [ ] Tests cover alert creation, email suppression in fake mode, incomplete email settings, and no alerts for normal admin actions.

## Blocked by

- Issue 003: Five-Minute Restore Helper and Retry Policy
