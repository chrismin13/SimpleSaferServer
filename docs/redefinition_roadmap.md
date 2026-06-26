# SimpleSaferServer Redefinition Roadmap

SimpleSaferServer is moving toward a smaller and safer shape: a local backup dashboard with optional managed modules.

The base app should be easy to install, update, and remove. It may read useful system state, but it should only write host state after an administrator enables a module and accepts a clear plan.

This roadmap targets clean installs only. Do not add migration code, old-install compatibility
branches, or hidden fallbacks for earlier layouts.

## Product Contract

Base SimpleSaferServer owns only its own files:

- application files
- application config
- application data
- application logs
- the web service
- the worker service
- the Python runtime managed by `uv`

Everything else is module-owned and opt-in. A module must explain what it reads, what it writes, what tools it needs, what privileged actions it can run, and what uninstall removes.

The first-run experience should still guide users toward a full backup setup:

1. choose storage
2. enable local or network backup access
3. set up cloud backup
4. configure alerts
5. choose a schedule

Users may skip steps, but the dashboard should keep showing whether backup protection is complete.

## System Ownership Rules

SimpleSaferServer should use a native setup flow:

```text
check -> plan -> apply -> record ownership -> uninstall owned resources
```

Do not embed Ansible, Terraform, Salt, Puppet, or Chef as the normal setup engine. Those tools solve a larger outside-in server-management problem. SimpleSaferServer needs a small local ownership flow that can be shown clearly in the Web UI and terminal.

Every host-level write must have an owner. Uninstall should remove only resources that SimpleSaferServer owns by path, marker, manifest entry, or module contract.
Module apply records the planned ownership, and helper actions that write host files record the
exact files they actually wrote.

## Runtime Shape

Use systemd only to supervise SimpleSaferServer itself:

- `simple-safer-server-web.service`
- `simple-safer-server-worker.service`

Scheduled work should move into the worker service instead of generating one systemd timer and service per feature.

The `sss` terminal command is the shared operator surface. It exposes status, doctor checks, module
plans, module ownership apply/uninstall commands, and job commands. `sss-helper` is the allowlisted
privileged-action surface; it runs registered actions from JSON passed on stdin.

The generic module lifecycle is manifest-backed:

- `sss module check <module>` reports missing or available external tools without changing the host
- `sss module list` shows whether each module has been applied on the current machine
- `sss module plan <module>` shows the declared setup plan
- `sss module apply <module>` reruns checks, then records only apply-time ownership in `<data>/ownership.json`
- setup routes and helper actions record exact host resources only after they write them
- `sss module uninstall <module>` removes safe app-owned files and ownership records only when all
  of that module's current records can be cleaned up generically

Module-specific cleanup still needs to delete or undo real host resources safely. The generic
uninstall command refuses to remove ownership records when host resources, storage markers, fstab
entries, or other non-app-owned resources still need explicit cleanup.

The current privileged-access shape is:

- the web service runs as a normal `sss` user
- the worker service runs as the same `sss` user
- root-only actions go through the small allowlisted helper
- the helper never accepts arbitrary shell commands from the Web UI

Current helper-backed actions include alert config writes, Cloud Backup sync and rclone config
writes, DDNS updates, Samba share-file publishing and reloads, Samba user sync/removal,
Drive Health live probes and scheduled checks, storage safety checks,
managed-drive format/setup/mount/unmount actions, the scheduled mount check, restart, and shutdown.
The Web UI, worker, and `sss job run` use the helper client for these root-capable paths instead of
calling the underlying services directly.

## Module Direction

Modules stay in one repository, but their code should live together. New module work should move toward:

```text
simple_safer_server/modules/<module_name>/
```

Each module should provide:

- metadata
- routes and navigation items
- setup checks and plans
- jobs
- required tools
- owned resources
- privileged actions
- UI help text
- docs links

Feature modules should keep routes, services, jobs, docs links, owned resources, and plan metadata
together under `simple_safer_server/modules/`.
The module contract is the index for that feature: route metadata, navigation metadata, setup
plans, help text, required tools, worker jobs, ownership, and privileged actions should all live
there.

## Dependency Direction

The base installer should stop installing feature packages by default. Optional modules may ask for tools when they are enabled.

Default decisions:

- keep `uv` for the Python runtime
- remove git from the production install path
- replace `msmtp` with Python SMTP
- make rclone optional and always use a SimpleSaferServer-owned rclone config
- make Samba optional and keep the owned include-file pattern
- make managed drive support explicit and advanced
- make System Updates read-only by default, or remove it if ownership stays unclear
- treat outbound HTTPS certificates as a preflight or module requirement instead of part of a broad package pile

## UI Direction

Replace custom UI components over time. Use ready-made components where they reduce code and risk.

Default decisions:

- use Web Awesome as the component library
- serve pinned Web Awesome assets locally
- use htmx for server-rendered interactions
- keep small shared JavaScript for real client-side behavior only
- avoid React, Shadcn, Tailwind, Vite, webpack, and npm build tooling in the first redesign pass

Module help text should be structured and reused by pages, setup flows, tooltips, warnings, confirmations, empty states, errors, and docs links.

Important warnings belong visibly in the UI. Tooltips can explain labels, but they should not hide safety-critical information.

## Localization Direction

Ship English first, but keep UI copy ready for localization:

- centralize module copy
- avoid sentence fragments
- use gettext-ready strings for Python and Jinja text
- pass translated page strings to JavaScript as JSON
- use browser `Intl` for dates, numbers, and relative times
- avoid a JavaScript translation build step for now

## Testing Direction

Keep tests that protect dangerous behavior. Remove tests that only lock in implementation details.

Keep strong coverage for:

- ownership and uninstall behavior
- host-level file writes
- Samba publish and rollback
- rclone sync safety
- storage marker checks
- fstab edits
- auth and privileged action allowlists
- worker job locking and result recording
- module plan, apply, and uninstall flows

Use lighter tests for display-only UI behavior.
