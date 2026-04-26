# Architecture

SimpleSaferServer is a Flask application with a package-based architecture. The top-level
`app.py` remains as a compatibility entrypoint for existing service files, deployment commands,
and `python app.py` development usage.

## Application Composition

`simple_safer_server.app_factory.create_app()` is the composition root. It creates the Flask app,
Socket.IO wrapper, runtime/config managers, feature services, and blueprints.

Shared services are stored in `app.extensions["simple_safer_server"]` as an `AppServices`
container. Blueprints fetch dependencies from that container instead of importing `app.py`.

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

`simple_safer_server.adapters.command_runner.CommandRunner` is the first shared command execution
boundary. Cloud Backup rclone calls use it already. Future work should continue moving systemd,
package-manager, SMB, mount, and other subprocess-heavy behavior behind adapters.

Bandit skips generic subprocess rules because SimpleSaferServer is a local admin tool that
intentionally calls Debian system utilities. Subprocess use should still validate user-controlled
arguments before execution and document operational assumptions near the code.

## Compatibility Entry Points

Keep top-level compatibility modules until install, service, and operator documentation are
intentionally migrated to package entrypoints. Do not remove `app.py` just because the app factory
exists.
