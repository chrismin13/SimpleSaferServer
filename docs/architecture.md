# Architecture

SimpleSaferServer is a Flask application with a package-based architecture. The package entrypoints
are canonical: local development can use `python -m simple_safer_server`, while the installed
systemd service and hosted deployments run Gunicorn against `simple_safer_server.wsgi:app`.

The target architecture is described in `docs/redefinition_roadmap.md`: a small base app plus
optional managed modules. The existing route/service/adapter layout is still valid for current
code, but new work should move toward deep modules with explicit setup plans, owned resources,
privileged actions, jobs, and user-facing help text.

## Application Composition

`simple_safer_server.app_factory.create_app()` is the composition root. It creates the Flask app,
runtime/config managers, feature services, and blueprints. Module-owned blueprints are collected by
`simple_safer_server.modules.module_blueprints()` and registered in a loop so adding a module does
not require another list of route imports in the app factory.

Shared services are stored in `app.extensions["simple_safer_server"]` as an `AppServices`
container. Blueprints fetch dependencies from that container instead of importing the startup
entrypoint.

## Package Layout

- `simple_safer_server/core/`: module contracts, setup-plan primitives, ownership records, CLI
  helpers, worker/job primitives, and privileged-action routing.
- `simple_safer_server/modules/`: deep feature modules. A module should keep its routes, service
  code, adapters, jobs, setup behavior, help text, and docs links together.
  Alerts, DDNS, Cloud Backup, Drive Health, File Sharing, Storage, and System Updates are
  module-owned examples, including their routes, service code, docs links, and module plans.
  Module help is structured for UI reuse: field help, tooltips, empty states, confirmations,
  success messages, error explanations, and recovery actions live beside the module contract.
  Module contracts also declare current page/API route metadata and sidebar navigation metadata, so
  future shared templates do not need to rediscover module pages from hardcoded template lists.
  Worker jobs are declared on the module contract as well; the built-in job registry collects them
  from the module registry.
- `simple_safer_server/routes/`: Flask blueprints and thin HTTP adapters.
- `simple_safer_server/services/`: route-independent feature behavior.
- `simple_safer_server/adapters/`: boundaries for system commands, provider APIs, filesystem
  behavior, and fake-mode implementations.
- `simple_safer_server/web/`: shared API response and validation helpers.

Keep `__init__.py` files minimal. Put meaningful behavior in clearly named modules such as
`services/task_service.py`, `modules/ddns/service.py`, or `adapters/command_runner.py`.

## Route And Service Boundaries

Routes should parse HTTP input, call a service or helper, and return HTTP output. Routes are the
JSON boundary: API routes serialize service result objects with `simple_safer_server.web` helpers
and map app-level exceptions to Problem Details. System behavior belongs outside route modules.
Code that touches systemd, rclone, Samba, filesystems, SMTP, provider APIs, disks, or secrets
should live behind a service or adapter boundary.

Existing extracted services include task handling. Existing blueprints cover dashboard/tasks and
users. Alerts, DDNS, Cloud Backup, Drive Health, File Sharing, Storage, and System Updates live
under `simple_safer_server/modules/`.
File Sharing keeps both its page route and SMB API routes under its module blueprint.

New host-writing behavior should use a SimpleSaferServer-native setup lifecycle:

```text
check -> plan -> apply -> record ownership -> uninstall owned resources
```

Plans should be reusable from the Web UI and the `sss` terminal command. They should say what will
change, what will not change, what tools are required, and which resources become owned by
SimpleSaferServer. `sss doctor` is read-only and reports runtime paths, registered privileged
actions, and module tool visibility without installing missing tools.
`sss module check <module>` runs the same read-only module tool checks for one module. It reports
missing required tools as blocking setup checks, but it does not install packages or change config.
Host-writing module routes must reject config writes until the module has an ownership record from
the apply/setup flow.

The module API routes expose the same registry, plans, and lifecycle helpers:

- `GET /api/modules`
- `GET /api/modules/<slug>/check`
- `GET /api/modules/<slug>/plan`
- `POST /api/modules/<slug>/apply`
- `POST /api/modules/<slug>/uninstall`
- `GET /fragments/modules/<slug>/plan`

Module API responses include the module's structured `ModuleHelp` content so pages can render
purpose text, setup intro text, field help, tooltips, warnings, empty states, confirmations,
success messages, error explanations, recovery actions, and docs links without copying text out of
markdown files.
They also include whether the module has been applied on the current machine. That `applied` value
comes from the ownership manifest, not from static module metadata. They also include module route
and navigation metadata. The base template renders module sidebar links from that navigation
metadata, so new module pages should add their page route and nav item to the module contract at
the same time they add the blueprint route.
Every route in a module blueprint must also be declared in that module's `ModuleRoute` metadata
with the same rule, endpoint, and HTTP methods. This keeps the module contract useful as the
feature index for the Web UI, CLI, docs, tests, and future setup tooling instead of letting route
knowledge drift back into the Flask app only.
Worker job metadata is exposed from the same module payload, so a module's scheduled behavior stays
beside its setup plan and help text.

The module plan fragment renders the same plan data through
`templates/partials/module_plan_preview.html`. It is read-only and does not apply or uninstall a
module; privileged changes still go through the explicit API or `sss` CLI lifecycle commands.

`sss module apply <module>` reruns the module's read-only requirement checks and refuses to apply
when any non-optional tool is missing. When checks pass, it records the module's declared owned
resources in the ownership manifest at `<data>/ownership.json`. `sss module uninstall <module>`
removes safe app-owned files declared with explicit placeholders such as `<config>/smtp.conf`,
then removes app-owned config sections or secret keys declared with explicit identifiers such as
`<config>/config.conf[ddns]` or `<config>/.secrets[duckdns_token]`. It removes the module's
manifest records only when every current ownership record is safe for generic cleanup. If a module
owns host files, storage markers, fstab entries, or other resources that need explicit cleanup,
generic uninstall stops and leaves the ownership manifest intact. Host-file deletion must stay
module-specific so SSS never removes an administrator-owned path by guessing from a text identifier.
Read-only modules can expose plans and status, but they reject apply and uninstall actions.

Privileged helper actions that write host files also record the concrete file they wrote in the
same ownership manifest. This keeps the manifest tied to real writes, not only to the setup plan
shown before a module is enabled.

Storage location checks live in `simple_safer_server.modules.storage.location`. That service owns
the small marker file inside the configured storage folder and the read/write checks that run before
Cloud Backup. Routes and worker jobs should use that service instead of open-coding storage safety
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
execution boundary. Task logs, status, and run history come from the worker job state instead of
feature-specific systemd units. `RcloneAdapter` wraps rclone process creation used by scheduled
Cloud Backup runs, `StorageCommandAdapter` wraps dashboard storage controls, and
`BackupDriveCommandAdapter` wraps managed backup-drive setup and detach commands.
`SystemUpdatesCommandAdapter` wraps read-only System Updates lock checks and Livepatch status reads.
`DriveHealthCommandAdapter` wraps SMART, HDSentinel, backup-drive lookup, and alert email commands.
New runtime behavior should live under `simple_safer_server/`; do not add top-level Python modules
for app services or route helpers.

Bandit skips generic subprocess rules because SimpleSaferServer is a local admin tool that
intentionally calls Debian system utilities. Subprocess use should still validate user-controlled
arguments before execution and document operational assumptions near the code.

The installed Web UI and worker run as the non-root `sss` service user. Web routes, CLI job
commands, and worker jobs must not call privileged binaries directly. They should call the shared
helper client for actions that need root.

`simple_safer_server.core.privileged_actions` registers allowed actions, and `sss-helper` runs one
registered action from a JSON payload on stdin. Passing payloads on stdin keeps secrets out of
process arguments. On installed systems, non-root callers run `sss-helper` through the installer
managed sudoers rule for `/usr/local/bin/sss-helper`.

Web routes, CLI job commands, and worker jobs should call
`simple_safer_server.core.privileged_client.PrivilegedActionClient` for helper-backed actions
instead of calling root-capable services directly. The current Web UI uses that client for SMTP
config writes, rclone config writes, Samba share-file publishing and reloads, Samba user
sync/removal, Drive Health live probes, managed-drive setup, storage
unmounts, storage mounts, storage formatting, restart, and shutdown. The worker uses helper actions
for Cloud Backup, DDNS, scheduled Drive Health, and the managed-drive mount check.
Helper-backed file writers record their owned config files after the write succeeds.

Current helper actions:

- `alerts.write-smtp-config`
- `cloud-backup.sync`
- `cloud-backup.write-rclone-config`
- `ddns.update`
- `drive-health.page-check`
- `drive-health.refresh-summary`
- `drive-health.scheduled-check`
- `file-sharing.reload`
- `file-sharing.remove-user`
- `file-sharing.sync-user`
- `file-sharing.write-shares`
- `storage.format`
- `storage.managed-drive`
- `storage.managed-unmount`
- `storage.mount`
- `storage.mount-check`
- `storage.safety-check`
- `storage.unmount`
- `system.poweroff`
- `system.reboot`

`storage.managed-drive` accepts only `partition`, `mount_point`, and `ntfs_driver` payload fields.
It reuses the storage module's rollback-aware managed-drive setup flow.

New privileged behavior must be declared as a module privileged action and wired through the shared
action registry. Do not add helper paths that accept arbitrary shell commands, raw argv fragments,
or unregistered action names.

## Web And Worker Services

The target runtime uses one Web service and one worker service. The Web service handles pages,
APIs, login, setup, and status. The worker service handles scheduled and long-running jobs.
Both services run as `sss`; root-only work goes through `sss-helper`.

Do not add new generated systemd timers for feature work. New scheduled behavior should be modeled
as a job that the worker can run from SimpleSaferServer-owned schedule state.

`sss job run ddns-update`, `sss job run cloud-backup`, and matching
`simple_safer_server.worker --run-job ...` commands dispatch to module code through the same job
runner. Manual and scheduled jobs do not run until their owning module has been applied. The worker
owns the recurring DDNS and Cloud Backup schedules instead of feature-specific systemd timers.

## Runtime Boundaries

Standalone proof-of-concept scripts should be removed when their behavior is available through the
app. Feature jobs belong in module code and should run through the worker/helper path. Root-level
files are reserved for repository metadata, install/deploy entrypoints, public docs, and developer
tools such as the pinned ShellCheck runner.
