# Issue 003: Five-Minute Restore Helper and Retry Policy

Type: AFK

## Parent

PRD: Disable Scheduled Task Schedules

## What to build

Add the background restore path for temporary disabled schedules. A single global systemd restore timer runs every five minutes with persistent catch-up behavior. The helper scans durable disabled-timer state, restores expired temporary disables without depending on the web UI, and applies the three-attempt restore failure policy.

## Acceptance criteria

- [ ] A single global restore service and timer are generated or installed for SimpleSaferServer.
- [ ] The restore timer runs every five minutes and uses persistent systemd timer behavior.
- [ ] The restore helper exits harmlessly when no temporary disabled schedules exist.
- [ ] Expired temporary disables are restored by enabling the corresponding systemd timer and removing the disabled record.
- [ ] Future temporary disables and permanent disables are left unchanged.
- [ ] Multiple disabled timers are handled in one restore run.
- [ ] Restore failures increment retry metadata and are retried on later five-minute runs.
- [ ] After three failed attempts for a timer, the record is marked restore failed and no longer retried automatically.
- [ ] Other timers continue to be restored even if one timer has reached restore failed.
- [ ] Manual Enable Schedule can recover a restore-failed timer and clears retry metadata on success.
- [ ] Tests cover empty state, expired state, future state, multiple timers, retry increments, retry limit, and manual recovery.

## Blocked by

- Issue 001: Disable and Enable Schedule Core Path
