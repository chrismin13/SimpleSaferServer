# Subprocess Timeouts

## Context

Review feedback identified admin-request subprocess calls that could block indefinitely.

## Decisions

- Add bounded timeouts to short command adapters used by setup, users, Samba, storage probes,
  systemd status/actions, and Ubuntu Pro/livepatch helpers.
- Leave intentionally long-running or lifecycle operations unbounded where a fixed duration is not
  predictable: rclone sync, apt workers, reboot, and poweroff.
- Enforce the rule with `tests/test_subprocess_timeouts.py`, which scans production
  `CommandRunner.run(...)` calls for explicit `timeout=` unless the call is allowlisted.
