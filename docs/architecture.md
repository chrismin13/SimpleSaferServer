# Architecture

SimpleSaferServer is a Flask application with a package-based architecture. The package entrypoints
are canonical: local development can use `python -m simple_safer_server`, while the installed
systemd service and hosted deployments run Gunicorn against `simple_safer_server.wsgi:app`.

## Application Composition

`simple_safer_server.app_factory.create_app()` is the composition root. It creates the Flask app,
runtime/config managers, feature services, and blueprints.

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

Routes should parse HTTP input, call a service or helper, and return HTTP output. Routes are the
JSON boundary: API routes serialize service result objects with `simple_safer_server.web` helpers
and map app-level exceptions to Problem Details. System behavior belongs outside route modules.
Code that touches systemd, rclone, Samba, filesystems, SMTP, provider APIs, disks, or secrets
should live behind a service or adapter boundary.

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
New runtime behavior should live under `simple_safer_server/`; do not add top-level Python modules
for app services or route helpers.

Bandit skips generic subprocess rules because SimpleSaferServer is a local admin tool that
intentionally calls Debian system utilities. Subprocess use should still validate user-controlled
arguments before execution and document operational assumptions near the code.

The installed service normally runs as root, so runtime adapters should invoke privileged binaries
directly instead of prepending `sudo`. Operator documentation can still show `sudo` commands because
humans often start from a non-root shell, and process-detection code may still recognize
operator-started commands that include `sudo`.

## Legacy And Compatibility Code

Standalone proof-of-concept scripts should be removed when their behavior is available through the
app. The legacy import tool remains available for bundles produced by
`https://github.com/chrismin13/SimpleSaferServer-old`; remove it only after that migration path is no
longer needed. Root-level files are reserved for repository metadata, install/deploy entrypoints,
public docs, and operator scripts.
