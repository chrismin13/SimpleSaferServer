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

Existing extracted services include task handling, DDNS, Cloud Backup, storage location checks, and alerts. Existing
blueprints cover dashboard/tasks, DDNS, Cloud Backup, System Updates, alerts, SMB, users, storage,
and drive health.

Storage location checks live in `simple_safer_server.services.storage_location`. That service owns
the small marker file inside the configured storage folder and the read/write checks that run before
Cloud Backup. Routes and scripts should use that service instead of open-coding storage safety
checks, because the failure mode can delete remote files when `rclone sync` sees the wrong local
folder.

The same module also exposes passive display status for the Dashboard and Storage page. Passive
status must not read the marker, list the storage folder, or create the write-probe file. Page loads
should not wake sleeping backup drives. Full validation belongs on explicit storage actions and
right before Cloud Backup, where the drive is about to be used anyway.

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
`SetupCommandAdapter` wraps setup wizard disk-format and SMB enable commands.
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

## Rclone connection editor

`routes/rclone_config.py` exposes an explicit action vocabulary under
`/api/cloud_backup/rclone/` (admin) and `/api/setup/cloud-backup/rclone/` (first-run setup,
then admin). Requests require the `X-SSS-Rclone: 1` header, JSON mutations, and normal session
authorization; CORS is not enabled. Responses cannot be cached. `state` lists remote names and
types; `raw` and private draft questions are the credential-editing surfaces.

`RcloneConfigService` owns session-bound, revisioned, expiring drafts and atomic publication.
`RcloneWorker` runs authenticated loopback RC processes against private mode-0600 files under
`runtime.volatile_dir/rclone`, with mode-0700 directories and no ambient `RCLONE_*` overrides.
Credentials travel in JSON, while RC authentication uses private environment variables. Worker
output is discarded. Provider errors are returned only to the editor, without request payloads
or credential-bearing logs. No arbitrary RC passthrough exists.

`config/providers` supplies the catalog. Non-interactive `config/create` and `config/update`
return opaque state plus question metadata. Jobs are polled asynchronously. Back restores both
a config checkpoint and its state by restarting the worker; cancellation/expiry terminates it.
The frontend has two shared OAuth presentations (`config_is_local` and `config_token`), with a
generic renderer for all other questions. New backends do not require an SSS provider registry.

The renderer interprets `Examples` as visible choices and `Exclusive` as a restriction on custom
entry. These are independent properties: a string question can offer choices and still accept
arbitrary text. Small choice sets use radio groups; large sets use a dropdown and selected-item
help. Selection keys are separate from submitted values, including empty values. `DefaultStr`
preserves rclone's serialized defaults, `Required` controls empty input when no default exists,
and `IsPassword` takes precedence over other presentation hints. Boolean and tri-state types have
dedicated choices. Other types use text (multiline for JSON-named fields or multiline defaults),
so rclone retains authority over units, sentinels, list syntax, validation and provider branching.
Unknown types remain editable without adding a provider-specific field mapping.

The shipped server uses one threaded worker. Draft state is process-local (maximum four open
editors, one per browser session); multi-worker deployments need a shared editor coordinator.
A cleanup thread expires idle drafts after 30 minutes and normal process exit closes workers.
Volatile drafts are not configuration backups and are discarded on restart.

Publication compares the config and selected destination with the editor's starting revision.
The stable `rclone.conf.sss.lock` is shared with production and fake-mode sync jobs. The backup
holds it before reading destination settings through completion of rclone, including token
refresh. Web saves fail promptly while the lock is held. The config is atomically published
before related settings; an ordinary settings/timer failure restores the prior file. Two files
cannot be one crash-atomic filesystem transaction; inspect configuration after an interrupted
system update or hard shutdown. External rclone processes do not honor the SSS lock automatically.
Cancellation and expiration preserve nonempty OAuth token updates when they are the only configuration
changes. Cleanup uses the publication lock and rechecks the saved config against the draft's base
before writing, without changing destination settings. If the lock is busy, the draft remains
open for retry; if the saved config changed, cleanup discards the draft without publishing.
Expired drafts delayed by a busy lock or failed file write retain their original expiry time,
so the cleanup thread retries on its next one-minute pass. They count toward the four-draft
limit. Unexpected cleanup failures are logged by exception type and cannot stop that thread.
Destination access tests use the frontend's shared draft cleanup path, refresh the saved version
after token publication, and expose a close retry when the draft must remain open.

See [Cloud Backup](cloud_backup.md) for configuration paths and authentication behavior, and
[rclone's RC API](https://rclone.org/rc/) and
[non-interactive configuration](https://rclone.org/commands/rclone_config_create/) for the upstream
protocol. `tests/test_rclone_config.py` exercises it against installed rclone using temporary
local storage and a local OAuth token issuer. Run it with
`uv run pytest tests/test_rclone_config.py`; these integration tests skip when rclone is absent.
`tests/test_rclone_editor_ui.py` also exercises rendering and answer selection across synthetic
metadata combinations and every option in the installed provider catalog. Run it with Node.js
on `PATH`; the catalog check additionally needs rclone. These checks cover field presentation and
value preservation, not successful authorization with every external provider.
Fake-mode account and folder operations still contact the selected provider.
