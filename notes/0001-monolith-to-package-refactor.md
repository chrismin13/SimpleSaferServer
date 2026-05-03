# 0001 Monolith To Package Refactor

## Summary

This note preserves the full work history of moving SimpleSaferServer from a flat legacy Flask
application toward a package-based architecture. It replaces `ROADMAP.md` as the historical task
record for this refactor.

The durable architecture guidance from this task now lives in `docs/architecture.md`; the durable
coding and quality standards remain in `docs/development.md`.

## Rules / Constraints

- Keep every phase behavior-preserving unless a bug is clearly found and documented.
- Keep slices small enough to review without a broad formatting-only sweep.
- Preserve Python 3.7 compatibility for Debian 10.
- Move touched code toward `docs/development.md` without unrelated churn.
- Update related docs and `index.html` links when behavior, commands, architecture, or developer workflow changes.
- Check `uninstall.sh` whenever a phase adds installed files, generated state, timers, services, config, or directories.
- Mark a phase complete only after verification has run and remaining debt is recorded.

## Target State

Refactored code lives under `simple_safer_server/`:

- `simple_safer_server/routes/`: Flask blueprints and thin HTTP adapters.
- `simple_safer_server/services/`: route-independent feature behavior.
- `simple_safer_server/adapters/`: boundaries for systemd, rclone, filesystem, provider APIs, and fake-mode implementations.
- `simple_safer_server/web/`: shared API response and validation helpers.

The long-term goal is for `app.py` to remain a thin compatibility entrypoint that delegates to an
app factory. Services must not import `app.py`; blueprints should receive shared dependencies
through the Flask app service container.

## Phase Checklist

- [x] Phase 0: Create the living roadmap and document the target architecture.
- [x] Phase 1: Add package scaffold and the app service container.
- [x] Phase 2: Extract task/status/fake-task behavior into `TaskService`.
- [x] Phase 3: Move dashboard and task routes into blueprints.
- [x] Phase 4: Extract DDNS service and blueprint.
- [x] Phase 5: Extract Cloud Backup service and blueprint.
- [x] Phase 6: Add shared web response and validation helpers.
- [x] Phase 7: Extract remaining route groups and services.
- [x] Phase 8: Introduce an app factory while keeping a compatibility `app.py`.
- [x] Phase 9: Tighten advisory gates one at a time.
- [x] Phase 10: Make quality gates strict.
- [x] Phase 11: Add the first command adapter boundary.
- [x] Phase 12: Fix stale blueprint endpoint references found by fake-mode dashboard rendering.
- [x] Phase 13: Replace Eventlet deployment/runtime path with Flask-SocketIO threading mode.

## Work Log

### Phases 0-2

- Added the `simple_safer_server/` package scaffold.
- Added `AppServices` as the shared service container.
- Added `TaskService` for scheduled task registry, task status/log operations, and fake task execution.
- Wired `TaskService` into `app.extensions["simple_safer_server"]` for future blueprints.
- Updated `app.py` task-related routes to call the task service while keeping URLs and response payloads unchanged.
- Added focused task service tests.

Docs and uninstall impact:

- `docs/development.md` pointed refactor work at the roadmap and package layout at this stage.
- `index.html` did not need updates because public documentation links did not change.
- `uninstall.sh` did not need updates because these phases added only source, tests, and docs.

Verification:

- Python 3.7 syntax compatibility check: passed.
- Focused Ruff check for `app.py`, `simple_safer_server/`, and `tests/test_task_service.py`: passed.
- Focused Pyright check for `simple_safer_server/` and `tests/test_task_service.py`: passed.
- Full pytest: 138 passed.
- Full Ruff: advisory failure remained with 128 legacy findings outside the completed task-service slice.
- Full Pyright: advisory failure remained with 53 errors and 18 warnings, mostly legacy optional fake-state typing, missing third-party import resolution, and test module monkeypatch typing.
- Full Bandit: advisory failure remained with 192 low and 6 medium findings, mostly subprocess review items and the existing all-interface development bind default.

### Phases 3-4

- Moved dashboard, task detail, task log, task start/stop, task run, and task schedule API routes into `simple_safer_server/routes/tasks.py`.
- Moved DDNS page and API routes into `simple_safer_server/routes/ddns.py`.
- Added `DdnsService` for DDNS config payloads, validation, secret-preserving saves, status-file reads, and task triggering.
- Expanded `AppServices` so blueprints can get shared runtime, config, system, task, and DDNS services through `current_app.extensions["simple_safer_server"]`.
- Updated template links to use blueprint endpoint names while keeping public URLs unchanged.
- Added focused DDNS service tests.

Docs and uninstall impact:

- `docs/ddns.md`, `docs/dashboard.md`, and `index.html` described unchanged user/operator behavior, so no link or behavior docs changed.
- `uninstall.sh` did not need updates because these phases added only source, tests, and docs.

Verification:

- Python 3.7 syntax compatibility check for touched application and test files: passed.
- Focused Ruff check for `app.py`, `simple_safer_server/`, `tests/test_task_service.py`, and `tests/test_ddns_service.py`: passed.
- Focused Pyright check for `simple_safer_server/`, `tests/test_task_service.py`, and `tests/test_ddns_service.py`: 0 errors, with import-resolution warnings for Flask and psutil.
- Focused pytest for task/DDNS services: 8 passed.
- Full pytest: 142 passed.

### Phase 5

- Moved Cloud Backup page and API routes into `simple_safer_server/routes/cloud_backup.py`.
- Added `CloudBackupService` for cloud backup config payloads, MEGA/rclone saves, task status/manual runs, MEGA folder browse/create, schedule saves, and MEGA credential validation.
- Kept rclone subprocess behavior in the service for this phase; a later adapter pass should isolate subprocess execution and temporary config file handling further.
- Updated the sidebar link to use the Cloud Backup blueprint endpoint while keeping `/cloud_backup` and all `/api/cloud_backup/*` URLs unchanged.
- Added focused Cloud Backup service tests.

Docs and uninstall impact:

- `docs/cloud_backup.md`, `docs/setup.md`, and `index.html` described unchanged user/operator behavior, so no docs links changed.
- `uninstall.sh` did not need updates because this phase added only source and tests.

Verification:

- Python 3.7 syntax compatibility check for touched application and test files: passed.
- Focused Ruff check for `app.py`, `simple_safer_server/`, and focused service tests: passed.
- Focused Pyright check for `simple_safer_server/` and focused service tests: 0 errors, with import-resolution warnings for Flask and psutil.
- Focused pytest for task/DDNS/Cloud Backup services: 12 passed.
- Full pytest: 146 passed.

### Phase 6

- Added `simple_safer_server/web/api.py` with shared JSON success/error helpers and JSON-object payload validation.
- Applied the helpers to the extracted DDNS and Cloud Backup blueprints only, avoiding a broad route sweep.
- Added focused tests for the web API helpers.

Docs and uninstall impact:

- No user/operator behavior changed, so no docs or `index.html` updates were needed.
- `uninstall.sh` did not need updates because this phase added only source and tests.

Verification:

- Python 3.7 syntax compatibility check for touched application and test files: passed.
- Focused Ruff check for `app.py`, `simple_safer_server/`, and focused service/helper tests: passed.
- Focused Pyright check for `simple_safer_server/` and focused service/helper tests: 0 errors, with import-resolution warnings for Flask and psutil.
- Focused pytest for helper/task/DDNS/Cloud Backup tests: 15 passed.
- Full pytest: 149 passed.

### Phase 7

- Moved System Updates page and API routes into `simple_safer_server/routes/system_updates.py`.
- Moved alerts/email notification routes into `simple_safer_server/routes/alerts.py`.
- Added `AlertsService` for email settings, notification toggles, and test email sending.
- Moved SMB routes into `simple_safer_server/routes/smb.py`.
- Moved user-management routes into `simple_safer_server/routes/users.py`.
- Moved storage mount/unmount and backup-drive API routes into `simple_safer_server/routes/storage.py`.
- Moved drive-health routes into `simple_safer_server/routes/drive_health.py`.
- Reused the existing `SystemUpdatesManager` as the service boundary and exposed it through `AppServices`.
- Applied shared web API helpers to the extracted route groups where response payloads were already JSON-shaped.
- Updated sidebar and task-detail links to use blueprint endpoint names while keeping public URLs unchanged.

Docs and uninstall impact:

- User/operator behavior did not change, so feature docs and `index.html` links did not need updates.
- `uninstall.sh` did not need updates because this phase added only source and tests.

Verification:

- Python 3.7 syntax compatibility check for touched application and test files: passed.
- Focused Ruff check for `app.py`, `simple_safer_server/`, and focused tests: passed.
- Focused Pyright check for `simple_safer_server/` and focused tests: 0 errors, with import-resolution warnings for Flask and psutil.
- Focused pytest for System Updates plus extracted service/helper tests: 37 passed.
- Full pytest: 153 passed.

### Phase 8

- Added `simple_safer_server/app_factory.py` with `create_app()` as the package-level composition root.
- Moved Flask setup, Socket.IO setup, logging, service construction, blueprint registration, context processors, auth routes, and error handlers out of top-level `app.py`.
- Kept top-level `app.py` as the compatibility entrypoint for existing service files, deployment commands, and `python app.py` development usage.
- Preserved existing route URLs and template behavior while making the app factory the long-term extension point.

Docs and uninstall impact:

- Runtime commands and service entrypoints still used `app.py`, so install/setup docs and `index.html` links did not need behavior updates.
- `uninstall.sh` did not need updates because this phase added only source.

Verification:

- Python 3.7 syntax compatibility check: passed.
- Full pytest: 153 passed.
- Focused Ruff check for `app.py`, `simple_safer_server/`, and focused tests: passed.

### Phase 9

- Updated `.github/workflows/quality.yml` so pytest became a strict CI gate.
- Updated `docs/development.md` to document that pytest was strict while Ruff, Pyright, Bandit, and dependency audit checks remained advisory during the cleanup pass.
- Kept advisory gates visible instead of forcing broad churn into the behavior-preserving refactor.

Docs and uninstall impact:

- `docs/development.md` was updated for the developer workflow change.
- `index.html` did not need updates because documentation URLs did not change.
- `uninstall.sh` did not need updates because this phase changed only source, tests, docs, and CI metadata.

Verification:

- Python 3.7 syntax compatibility check: passed for 58 Python files.
- Full pytest: 153 passed.
- Full Ruff: advisory failure remained with 124 legacy findings.
- Full Pyright: advisory failure remained with 37 errors and 31 warnings, mostly legacy optional fake-state typing, missing third-party import resolution, and test monkeypatch typing.
- Full Bandit: advisory failure remained with 188 low and 6 medium findings, mostly subprocess review items and the existing all-interface development bind default.

### Phase 10

- Resolved Ruff lint debt and made `ruff check` pass for the full repository.
- Ran the Ruff formatter once so `ruff format --check` can be enforced.
- Pointed Pyright at the local virtualenv and resolved the remaining application type errors.
- Added narrow Pyright suppressions for tests that intentionally monkeypatch modules or inspect dynamic JSON responses.
- Reviewed Bandit findings and made the security scan strict, with project-level skips only for generic subprocess rules that match SimpleSaferServer's local admin purpose.
- Centralized accepted Bandit skips for fixed-HTTPS DDNS calls, the headless-server bind default, command-token false positives, and generic subprocess rules.
- Made all CI quality gates strict in `.github/workflows/quality.yml`.

Docs and uninstall impact:

- `docs/development.md` documented the strict quality baseline and accepted Bandit subprocess policy.
- `index.html` did not need updates because documentation URLs did not change.
- `uninstall.sh` did not need updates because this phase changed only source, tests, docs, and CI metadata.

Verification:

- Python 3.7 syntax compatibility check: passed for 58 Python files.
- Ruff format check: passed.
- Ruff lint: passed.
- Pyright: passed with 0 errors and 0 warnings.
- Bandit: passed with no issues identified.
- Dependency audit: passed with no known vulnerabilities found, retaining the documented Debian 10 pytest advisory ignore.
- Full pytest: 153 passed.

### Phase 11

- Added `simple_safer_server/adapters/command_runner.py` as the first shared command execution boundary.
- Wired a shared `CommandRunner` through the app factory and service container.
- Migrated Cloud Backup rclone operations to the injected command runner.
- Added focused tests proving Cloud Backup uses the injected command runner for MEGA folder listing and credential validation.
- Preserved existing Cloud Backup response payloads and rclone command behavior.

Docs and uninstall impact:

- The target architecture already documented `simple_safer_server/adapters/`, so no user/operator docs or `index.html` links changed.
- `uninstall.sh` did not need updates because this phase added only package source and tests.

Verification:

- Focused Cloud Backup service tests: passed.

### Phase 12

- Fixed stale template endpoint references after blueprint extraction.
- Updated dashboard mount/unmount/restart/shutdown forms to use `storage_routes.*`.
- Updated the Drive Health navigation link to use `drive_health_routes.drives`.
- Added an app-factory render test for fake-mode `/dashboard` so stale template endpoint names fail in tests.

Docs and uninstall impact:

- User-facing URLs did not change.
- `index.html` did not need updates because documentation links did not change.
- `uninstall.sh` did not need updates because this phase changed only source and tests.

Verification:

- Python 3.7 syntax compatibility check: passed for 61 Python files.
- Ruff format check: passed.
- Ruff lint: passed.
- Pyright: passed with 0 errors and 0 warnings.
- Bandit: passed with no issues identified.
- Dependency audit: passed with no known vulnerabilities found.
- Full pytest: 156 passed.

### Phase 13

- Forced Flask-SocketIO to use `async_mode="threading"` so local fake mode no longer imports Eventlet.
- Replaced Eventlet deployment commands with Gunicorn `gthread`.
- Made Gunicorn thread count configurable through `WEB_THREADS`, with a default of `4`.
- Replaced the runtime dependency on `eventlet` with `simple-websocket`.
- Updated Railway/Nixpacks/Procfile and manual install docs.

Docs and uninstall impact:

- `docs/manual_install.md` now documents `simple-websocket` and `WEB_THREADS`.
- Deployment metadata changed; user/operator feature docs and `index.html` did not need updates.
- `uninstall.sh` did not need updates because no installed files, generated state, services, timers, config, or directories changed.

Verification:

- `timeout 5 ./run_fake.sh` showed the Eventlet deprecation warning was gone.
- `python -m json.tool railway.json`: passed.
- Ruff format check: passed.
- Ruff lint: passed.
- Pyright: passed with 0 errors and 0 warnings.
- Focused dashboard render test: passed.

## Decisions

- Keep `app.py` as a compatibility entrypoint until install, service, and operator docs intentionally move to package entrypoints.
- Use `notes/` for task history and handoff context, not canonical behavior documentation.
- Keep `docs/development.md` as the coding standard and `docs/architecture.md` as the durable architecture reference.
- Use Flask-SocketIO threading mode by default; Eventlet is deprecated and no current Socket.IO event handlers require it.
- Keep `WEB_THREADS` configurable instead of deriving it from CPU count, because deployment CPU quotas can be misleading and this is a small admin app.

## Follow-Up Backlog

- Continue moving subprocess-heavy operations behind adapters, especially systemd, package manager, SMB, and mount helpers.
- Keep top-level compatibility modules until install, service, and operator docs are intentionally migrated to package entrypoints.
