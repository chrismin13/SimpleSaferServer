# PRD: Disable Scheduled Task Schedules

## Problem Statement

SimpleSaferServer admins can manually start and stop scheduled task services, but they cannot temporarily or permanently disable a task's automatic systemd timer from the dashboard. When an admin is doing maintenance, troubleshooting, drive swaps, network work, or update work, they may need to stop future automatic task runs without disabling manual task execution.

Admins can use `systemctl disable --now` over SSH today, but the web UI will not clearly represent whether a timer was disabled by SimpleSaferServer or externally. It also cannot restore temporary disables automatically. This creates a gap between the admin dashboard and the systemd scheduler that actually runs the background tasks.

## Solution

Add schedule disable/enable controls for all managed scheduled tasks. Disabling a schedule disables the task's systemd `.timer`, not its `.service`, so manual **Start** remains available.

Admins can disable a schedule for quick preset durations or permanently. Temporary disables are stored as durable SimpleSaferServer state and are restored by one always-on systemd restore timer that runs every five minutes. The restore path does not depend on the web UI being available. If restore fails three times, SimpleSaferServer records an alert and sends email through the existing alert-notification behavior.

The dashboard keeps its existing compact table shape by folding schedule state into the existing `Next Run` field. Task detail provides the fuller control surface and explanatory modal. The dashboard right-click task menu includes the same task actions for consistency.

## User Stories

1. As an admin, I want to disable a scheduled task's automatic schedule, so that it does not run during maintenance.
2. As an admin, I want disabling a schedule to use systemd timer semantics, so that the task does not automatically run after reboot.
3. As an admin, I want Disable Schedule to stop the timer immediately, so that a pending automatic run is cancelled.
4. As an admin, I want Disable Schedule to leave the service manually startable, so that I can still run the task on demand.
5. As an admin, I want Start to remain available while a schedule is disabled, so that I can run the task intentionally.
6. As an admin, I want Stop to remain separate from Disable Schedule, so that I do not accidentally interrupt an active task when only future runs should stop.
7. As an admin, I want to disable a schedule for 1 hour, so that short maintenance does not require me to remember to re-enable it.
8. As an admin, I want to disable a schedule for 6 hours, so that same-day work can complete without automatic task interference.
9. As an admin, I want to disable a schedule for 24 hours, so that overnight maintenance can avoid scheduled jobs.
10. As an admin, I want to disable a schedule for 7 days, so that extended maintenance or travel windows can avoid automatic runs.
11. As an admin, I want to disable a schedule permanently, so that I can opt out of an automatic task until I explicitly re-enable it.
12. As an admin, I want Permanent disable to have extra confirmation clarity, so that I understand it will not restore automatically.
13. As an admin, I want disabling a schedule again to replace the previous expiry, so that the web UI always reflects the current selected duration.
14. As an admin, I want a temporary disable changed to Permanent to stop restoring automatically, so that my latest intent wins.
15. As an admin, I want a Permanent disable changed to a temporary duration to restore automatically later, so that I can reverse an indefinite choice without first enabling it.
16. As an admin, I want Enable Schedule to immediately restore a disabled schedule, so that I can recover from temporary, permanent, or external disables.
17. As an admin, I want Enable Schedule to be low-friction, so that restoring normal operation is fast.
18. As an admin, I want the dashboard to show disabled schedule state in the Next Run field, so that mobile users do not get another table column.
19. As an admin, I want short schedule labels, so that task rows remain scannable.
20. As an admin, I want today's times displayed compactly, so that common schedules do not waste space.
21. As an admin, I want tomorrow's times labelled as Tomorrow, so that I do not confuse them with today's schedule.
22. As an admin, I want later dates shown with a month/day label, so that multi-day disables are unambiguous.
23. As an admin, I want temporary disables shown as `Disabled until 18:00`, so that I know when automatic scheduling returns.
24. As an admin, I want permanent disables shown as `Disabled`, so that I know automatic scheduling is off indefinitely.
25. As an admin, I want externally disabled timers shown as `Disabled externally`, so that the dashboard does not claim SimpleSaferServer created the state.
26. As an admin, I want unexpected timer states shown as `Schedule issue`, so that the dashboard does not present misleading next-run data.
27. As an admin, I want task detail to show raw systemd state for schedule issues, so that I have enough information to inspect or repair the host.
28. As an admin, I want task detail to point me toward System Updates or reinstall when generated units look broken, so that I know the likely repair path.
29. As an admin, I want no special masked-unit recovery flow, so that rare manual systemd mistakes do not complicate the product.
30. As an admin, I want externally disabled timers to be enableable from the UI, so that I can recover normal scheduling without SSH.
31. As an admin, I want Disable Schedule to take ownership of an externally disabled timer, so that future restoration can be managed by SimpleSaferServer.
32. As an admin, I want active SimpleSaferServer disable records to be authoritative until expiry, replacement, or manual enable, so that temporary disable behavior is predictable.
33. As an admin, I want app updates and generated unit refreshes to preserve active SimpleSaferServer disables, so that maintenance windows are not silently undone.
34. As an admin, I want the restore mechanism to work without the web UI running, so that background scheduling remains independent of dashboard availability.
35. As an admin, I want one global restore timer, so that the system does not generate many per-task restore units.
36. As an admin, I want the restore timer to run every five minutes, so that the implementation stays simple and restoration is close enough to the requested expiry.
37. As an admin, I want restore behavior to be persistent across reboot, so that a schedule disabled until a time restores after the host comes back.
38. As an admin, I want the restore helper installed and enabled during normal install/setup, so that restore behavior is always available.
39. As an admin, I want the restore helper to be harmless before setup is complete, so that first-run setup still keeps main recurring timers inactive.
40. As an admin, I want restore failures retried a limited number of times, so that transient failures get a chance to recover without retrying forever.
41. As an admin, I want restore failures to create alerts after three failed attempts, so that I am notified when automatic scheduling did not return.
42. As an admin, I want restore failure alerts to use existing alert and email settings, so that notifications are consistent with the rest of the app.
43. As an admin, I do not want normal disable/enable actions to send alerts, so that intentional maintenance actions do not create notification noise.
44. As an admin, I want fake mode to simulate disabled schedules, so that I can test and demo the workflow without systemd.
45. As an admin, I want right-click task actions to include Disable Schedule and Enable Schedule, so that dashboard shortcuts remain consistent.
46. As an admin, I want Disable Schedule to open a modal, so that the app can explain the effect before I choose a duration.
47. As an admin, I want the modal to avoid dynamic layout shifts, so that the control feels stable on desktop and mobile.
48. As an admin, I want custom date/time selection deferred, so that the first version ships with a simpler and reliable duration picker.

## Implementation Decisions

- Use the product language **Disable Schedule** and **Enable Schedule** in user-facing UI and docs.
- Disabling a schedule runs `systemctl disable --now` on the task timer only.
- Enabling a schedule runs `systemctl enable --now` on the task timer only.
- Manual task Start continues to start the task service and remains available while the schedule is disabled.
- Stop continues to stop the task service and does not imply future schedule changes.
- All five managed scheduled tasks support schedule disable/enable: Check Mount, Drive Health Check, Cloud Backup, DDNS Update, and App Update.
- Temporary duration options for the first version are 1 hour, 6 hours, 24 hours, and 7 days.
- Permanent disable is supported and does not automatically restore.
- Custom date/time disable is out of scope for the first version but the modal should leave room for it later.
- A new disable action replaces any existing SimpleSaferServer disable record for that timer.
- Durable disabled-timer state lives under the runtime data directory in `disabled_timers.json`.
- The disabled-timer state is operational state, not secret config and not volatile status.
- Write the SimpleSaferServer disabled-timer record only after the systemd disable command succeeds.
- For temporary disables, the restore helper discovers expired records on its next five-minute run.
- One global restore service/timer handles all temporary disabled timers.
- The global restore timer runs every five minutes and uses `Persistent=true`.
- The global restore helper is installed and enabled during normal install/setup.
- The restore helper may run before setup completion because it only acts on explicit SimpleSaferServer disable records.
- The restore helper does not depend on Flask or the web UI.
- Core disabled-timer state and restore behavior should live in a small service module with a testable interface.
- `TaskService` remains the web-facing owner for task summaries, schedule actions, and task detail behavior.
- `SystemdAdapter` should expose the systemd timer operations and state reads needed by the feature.
- Task summaries should include structured schedule state instead of forcing the UI to parse display labels.
- Schedule state should include enough information for display labels, source, expiry, restore failure, and raw systemd issue details.
- Dashboard display rolls schedule state into the existing `Next Run` field rather than adding a column.
- Active next-run labels use compact relative formatting: today's time only, Tomorrow for next day, and month/day for later dates.
- Disabled labels use compact relative formatting: `Disabled until 18:00`, `Disabled until Tomorrow 18:00`, `Disabled until May 16 18:00`, `Disabled`, `Disabled externally`, and `Restore failed`.
- If a SimpleSaferServer disable record exists, that record is authoritative until expiry, replacement, or manual enable.
- If no SimpleSaferServer disable record exists and systemd reports the timer disabled, show `Disabled externally`.
- If systemd reports an unexpected timer state, show `Schedule issue` and expose raw state on task detail.
- Do not implement special recovery flows for masked or manually broken systemd units.
- For unexpected states, guide the admin to fix systemd manually or regenerate units through System Updates or reinstall.
- Enable Schedule works for SimpleSaferServer-managed disables and externally disabled timers.
- Disable Schedule may take ownership of an externally disabled timer by creating a SimpleSaferServer record after successful systemd disable.
- Disable Schedule does not need systemd preflight checks; attempt the operation and create state only on success.
- App updates and generated unit refreshes must preserve active SimpleSaferServer disable records.
- Restore failures retry three times at five-minute intervals.
- After three failed restore attempts, keep the disabled record, mark it as restore failed, and stop retrying that timer automatically.
- Other disabled timers continue to be processed even if one timer is in restore-failed state.
- Manual Enable Schedule retries restore immediately for restore-failed timers.
- Successful manual enable clears retry metadata and removes the disable record.
- Failed manual enable leaves the failed state visible.
- Restore failure alerts use the existing alert and email-notification path.
- Normal disable and enable actions do not create alerts or send email.
- Restore events should be logged by the restore helper/app log, not individual task logs.
- Fake mode simulates disable/enable and restore behavior without invoking systemd.
- The dashboard right-click task menu includes Start, Stop, Disable Schedule, and Enable Schedule where applicable.
- Disable Schedule opens a modal with explanatory text and fixed duration choices.
- Permanent disable uses clearer friction in the modal, including text that it stays off until enabled manually.
- Avoid skip-next-run warnings in the first version to keep the modal stable.
- Uninstall must remove the restore service, restore timer, helper script, and disabled-timer state if app data is removed.
- Documentation should update dashboard, task detail, system update or install behavior where relevant, and the documentation links should be checked from the public index page.

## Testing Decisions

- Tests should assert external behavior and stable contracts, not private implementation details.
- The disabled-timer service module should have focused unit tests for state creation, replacement, permanent disables, temporary expiry, restore attempts, retry limits, restore-failed state, and manual enable recovery.
- The systemd adapter should have tests for enable, disable, and timer-state command shapes.
- Task service tests should assert schedule state in task summaries, including active, SimpleSaferServer disabled, externally disabled, restore failed, fake mode, and schedule issue cases.
- Route tests should cover Disable Schedule and Enable Schedule success, operation failure, JSON response shapes, authentication/authorization behavior, and missing task behavior.
- Restore helper tests should cover no-op empty state, expired restores, future disables, multiple timers, retry-limit alert creation, and independence from Flask.
- UI-oriented tests should assert rendered dashboard/task detail includes schedule controls and labels without adding a new dashboard column.
- Existing test prior art includes task route tests, task service tests, systemd adapter tests, system utils install tests, alert store tests, and dashboard rendering tests.
- Documentation behavior should be checked by reviewing the updated docs rather than snapshotting large rendered pages.
- Python 3.7 compatibility remains required for application code.

## Out of Scope

- Custom date/time selection for disable expiry.
- Per-task restore service/timer units.
- Dynamic exact-time re-arming of the restore timer.
- Special recovery actions for masked, malformed, missing, or manually broken systemd units.
- Detecting or preserving every possible external admin action after a SimpleSaferServer disable record is created.
- Sending alerts for normal admin-initiated disable or enable actions.
- Disabling task services; this feature only disables timers.
- Adding a new dashboard table column for schedule state.
- Editing `README.md`.

## Further Notes

- SimpleSaferServer is a root-run, admin-only local management tool. The UI can expose useful systemd state to trusted admins, but should avoid broad status leaks and avoid logging unrelated secrets.
- The implementation should prefer a deep disabled-timer module with a compact interface because it encapsulates durable state, systemd coordination, retry policy, and restore behavior.
- The restore helper should be a stable installed entrypoint that imports application service code rather than constructing the Flask app.
- The shared alert/email helper should avoid duplicating SMTP behavior and should be reusable by existing background health code.
- The first version should optimize for reliable operations and clear state display over exhaustive systemd diagnosis.
