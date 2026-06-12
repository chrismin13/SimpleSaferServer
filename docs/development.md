# Development & Coding Conventions

This document is the source of truth for how SimpleSaferServer code should be written, reviewed, and refactored.

New code should follow these conventions immediately. Existing code should move toward them when it is touched or during planned refactors, without unrelated formatting churn.

## Compatibility Target

SimpleSaferServer targets the latest stable CPython managed by `uv`, currently Python 3.14. The app does not use distro-provided Python as its runtime, and it does not support prerelease Python.

- `.python-version` selects the runtime for development, CI, and installed app environments.
- `pyproject.toml` defines app and development dependencies.
- `uv.lock` pins the exact resolved dependency graph used by CI and production installs.
- Use modern Python syntax and typing supported by the target Python version.
- Keep runtime dependencies small. Adding a dependency should remove meaningful code or operational risk.

## Published Standards We Follow

- **PEP 8** is the baseline for Python layout, naming, imports, and consistency.
- **PEP 20** is the readability and simplicity compass.
- **Google Python Style Guide** is the practical reference for large-codebase conventions.
- **Flask official patterns** guide application factories, blueprints, and larger application structure.
- **PEP 484** guides type hints.
- **PEP 257** guides docstrings.
- **Diataxis** guides user and operator documentation.
- **OWASP-style review** applies to admin, auth, secrets, subprocess, filesystem, and network-facing changes.
- **RFC 9457 Problem Details** and **OpenAPI** are future targets for API error and schema consistency.

## Flask Architecture

Routes should stay thin. A route should parse HTTP input, call a service or helper, and return HTTP output.

Feature routes should live in blueprints. `setup_wizard.py` already uses this pattern, and new feature modules should follow it.

System behavior belongs outside route modules. Code that touches systemd, rclone, Samba, filesystems, SMTP, provider APIs, disks, or secrets should live behind a small service or adapter boundary.

Fake mode should be an alternate implementation behind those boundaries. Avoid scattering `runtime.is_fake` conditionals through unrelated route logic.

Shared response and validation helpers should be preferred over per-route ad hoc response shapes. API routes should follow `docs/api_responses.md`: success responses use a `data` envelope, failures use Problem Details with real HTTP status codes, and services return Python objects or raise app-level exceptions instead of returning HTTP-shaped dictionaries.

Security work should follow the app's admin trust model. SimpleSaferServer is a root-run, admin-only local management tool, so do not hide useful managed credentials or configuration from administrators just for appearance. Credential editor endpoints may return the stored secret when that is the behavior the editor needs. Avoid accidental spread instead: keep secrets out of logs, broad status responses, process argv, unrelated UI, and overly broad filesystem permissions.

Avoid persistent writes unless the data must survive restart or is durable operator history/config. Use volatile runtime state for status/cache data that can be rebuilt.

Use `simple_safer_server.services.file_persistence` for app-owned file writes. Small JSON, INI, and text state/config files should be written through a same-directory temp file, fsynced when the file is durable, and published with `os.replace`. Cross-process read/modify/write state must use a stable sidecar lock file; do not lock the target file itself when the writer replaces that target. Append-heavy logs should stay append-oriented and use explicit retention or rotation instead of rewriting the whole file for every line.

`docs/architecture.md` describes the current package architecture. New code should move toward:

- `simple_safer_server/routes/` for Flask blueprints.
- `simple_safer_server/services/` for route-independent behavior.
- `simple_safer_server/adapters/` for system and fake-mode boundaries.
- `simple_safer_server/web/` for shared response and validation helpers.

Keep `__init__.py` files minimal. Put meaningful behavior in clearly named modules such as `services/task_service.py` or `routes/ddns.py`.

Do not add top-level Python modules for application runtime code. Put new route, service, adapter, web helper, or legacy migration behavior inside the `simple_safer_server/` package.

## Python Style

- Prefer explicit names and small functions.
- Avoid mutable module-level state except for application composition and carefully documented runtime state.
- Avoid broad `except Exception` except at HTTP or script boundaries where the caller must receive a controlled response.
- Internal code should raise specific exceptions that routes can map to HTTP responses.
- Use dataclasses, enums, or typed objects when repeated dictionaries or string constants are becoming a contract.
- Prefer frozen dataclasses for read-only service result objects, and use explicit `as_dict()` methods when serialized field names, secret filtering, or stable API aliases matter.
- Prefer structured parsers and standard library APIs over ad hoc string manipulation when practical.
- Keep comments focused on operational surprises, hidden assumptions, and future-forgettable behavior.
- Do not write comments or docs that assume the reader knows a previous implementation. Describe the current behavior directly.

### Accessors, Properties, And Service Methods

Do not add Java-style `get_x()` or `set_x()` methods for plain in-memory attributes. Python code should use direct attributes for passive data, and `@property` for cheap, side-effect-free derived facts that callers can reasonably treat like attributes.

Use explicit methods when access performs real work: persistence, validation, secrets handling, system commands, provider calls, fake-state mutation, or any other side effect. In those cases a method name should make the operation obvious. Prefer `list_*` for collection-returning service methods, and prefer behavior names such as `set_password()` when the method enforces policy or coordinates external state.

## Documentation Rules

Any behavior change should check the related docs and the documentation links in `index.html`.

User and operator behavior belongs in `docs/*.md`. Contributor-only rules belong here.

Chronological task notes belong in `notes/`. Notes are handoff history, not canonical documentation; move durable behavior, commands, architecture, and workflow details into the appropriate docs when they stop being task-specific.

When adding files, services, timers, state directories, generated artifacts, or system config, check whether `uninstall.sh` should remove them.

Remove standalone proof-of-concept scripts once their behavior is supported inside the app. If a script is retained only for operator migration, document that status and avoid expanding it.

## Frontend Rules

Use the `frontend-design` and `uncodixfy` skills for UI work.

Reuse existing Bunker interface patterns and check `docs/internal_ui_patterns.md` before adding new UI behavior.

## Dependency Management

Use uv for all Python dependency and environment management.

Install or refresh development dependencies with:

```bash
bash install_dev.sh
```

Add runtime dependencies to `[project].dependencies` in `pyproject.toml`. Add development-only dependencies to the `dev` dependency group. The `version = "0"` field is only inert Python project metadata; the app reports Git commits instead of package versions. Then refresh the lockfile:

```bash
bash update_lock.sh
```

For a targeted security or compatibility update, pass package names:

```bash
bash update_lock.sh cryptography Flask
```

The lockfile is committed because SimpleSaferServer is an application. CI and installs use `uv sync --frozen` so dependency resolution does not change during deployment.

## Quality Commands

Install the optional fast commit hooks with:

```bash
uv run pre-commit install
```

During normal development, run targeted tests for the code you changed. Before committing, run the fast local check wrapper:

```bash
bash check_ci.sh
```

`check_ci.sh` syncs the dev environment, formats Python with Ruff, formats shell scripts with shfmt, lints Python with Ruff, lints shell scripts with ShellCheck, runs pytest, and runs ty. The shell checks only look at tracked `.sh` files, so local virtualenv scripts and generated scratch files do not become part of the project quality gate. Full-suite pytest runs use `pytest-xdist` workers by default; set `PYTEST_WORKERS=4` or another worker count if `auto` is too aggressive on your machine. Pass pytest arguments after the script options for targeted serial runs:

```bash
bash check_ci.sh tests/test_drive_health.py
```

CI uses `bash check_ci.sh --check-format` so unformatted files fail instead of being edited in the container. ty is configured to check shipped Python code and scripts; tests use dynamic monkeypatching patterns that are better covered by pytest than by ty today. Dependency and security checks are split out because they are slower and do not need to run after every local edit:

```bash
bash check_security.sh
```

`check_security.sh` runs Bandit and `uv run pip-audit --local`. Run it before releases, after dependency changes, or when touching sensitive subprocess/auth/filesystem code.

When you need exact GitHub Actions reproduction, run:

```bash
bash check_ci_docker.sh
```

The Docker check uses the same uv/Python Debian image as `.github/workflows/python-ci.yml`.

## Current Baseline Policy

Continuous integration runs one uv-managed Python lane on the target stable Python version. If repository branch protection uses required status checks, update those required check names after workflow or job renames. The current workflow file is `.github/workflows/python-ci.yml`, with job `python-ci`.

Bandit skips the generic subprocess import/execution rules because SimpleSaferServer is a local admin tool that intentionally calls Debian system utilities. Keep those subprocess calls behind services or adapters, validate user-controlled arguments before shelling out, and document operational assumptions near the code.

Short `CommandRunner.run(...)` calls must pass an explicit `timeout=` so admin request handlers do not block forever on a wedged system command. Long-running supervised work such as apt workers, rclone sync, and lifecycle commands such as reboot or poweroff may be deliberately exempted in `tests/test_subprocess_timeouts.py`.
