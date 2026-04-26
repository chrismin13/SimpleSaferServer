# Architecture

SimpleSaferServer is a Flask application with a package-based architecture. The package entrypoints
are canonical: local/service startup uses `python -m simple_safer_server`, and WSGI deployments use
`simple_safer_server.wsgi:app`.

## Application Composition

`simple_safer_server.app_factory.create_app()` is the composition root. It creates the Flask app,
Socket.IO wrapper, runtime/config managers, feature services, and blueprints.

Shared services are stored in `app.extensions["simple_safer_server"]` as an `AppServices`
container. Blueprints fetch dependencies from that container instead of importing the startup
entrypoint.

## Package Layout

- `simple_safer_server/routes/`: Flask blueprints and thin HTTP adapters.
- `simple_safer_server/services/`: route-independent feature behavior.
- `simple_safer_server/adapters/`: boundaries for system commands, provider APIs, filesystem
  behavior, and fake-mode implementations.
- `simple_safer_server/web/`: shared API response and validation helpers.

Keep `__init__.py` files minimal. Put meaningful behavior in clearly named modules such as
`services/task_service.py`, `routes/ddns.py`, or `adapters/command_runner.py`.

## Route And Service Boundaries

Routes should parse HTTP input, call a service or helper, and return HTTP output. System behavior
belongs outside route modules. Code that touches systemd, rclone, Samba, filesystems, SMTP,
provider APIs, disks, or secrets should live behind a service or adapter boundary.

Existing extracted services include task handling, DDNS, Cloud Backup, and alerts. Existing
blueprints cover dashboard/tasks, DDNS, Cloud Backup, System Updates, alerts, SMB, users, storage,
and drive health.

## Fake Mode

Fake mode should be represented behind services or adapters. Avoid scattering `runtime.is_fake`
conditionals through unrelated route logic. When a fake-mode branch depends on fake state, make the
assumption explicit near the boundary.

## Command Execution

`simple_safer_server.adapters.command_runner.CommandRunner` is the shared low-level command
execution boundary. `SystemdAdapter` wraps task-related systemd and journalctl calls,
`RcloneAdapter` wraps rclone process creation used by scheduled Cloud Backup runs, and
`StorageCommandAdapter` wraps dashboard storage controls, and `BackupDriveCommandAdapter` wraps
managed backup-drive setup and detach commands. `SystemUpdatesCommandAdapter` wraps System Updates
package-manager, lock, config-write, Livepatch, and long-running apt worker commands.
`SetupCommandAdapter` wraps setup wizard disk-format, SMB enable, and MEGA picker commands.
`DriveHealthCommandAdapter` wraps SMART, HDSentinel, backup-drive lookup, and alert email commands.
Future work should continue moving deprecated legacy migration and top-level runtime modules behind
package modules where those modules remain part of the supported runtime.

Bandit skips generic subprocess rules because SimpleSaferServer is a local admin tool that
intentionally calls Debian system utilities. Subprocess use should still validate user-controlled
arguments before execution and document operational assumptions near the code.

## Legacy And Compatibility Code

Standalone proof-of-concept scripts should be removed when their behavior is available through the
app. The legacy import tool remains as a deprecated operator escape hatch, but it should not receive
new feature work. Top-level modules such as `backup_drive_setup.py`, `drive_health.py`, and
`system_updates.py` still contain active runtime behavior and should be migrated deliberately rather
than deleted as dead code.
