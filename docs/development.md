# Development & Coding Conventions

This document is the source of truth for how SimpleSaferServer code should be written, reviewed, and refactored.

New code should follow these conventions immediately. Existing code should move toward them when it is touched or during planned refactors, without unrelated formatting churn.

## Compatibility Target

SimpleSaferServer keeps Python 3.7 application compatibility for Debian 10 legacy installs, but
the strict security-supported baseline is Debian 13 / Python 3.13. Several upstream dependency
fixes no longer publish Python 3.7-compatible releases, so Python 3.7 is a compatibility lane, not
the dependency-audit lane.

Python 3.7 compatibility is a hard requirement for application code:

- Do not use `match` / `case`.
- Do not use `list[str]`, `dict[str, ...]`, `set[str]`, or `tuple[...]` annotations.
- Do not use `str | None` or other PEP 604 union syntax.
- Use `typing.List`, `typing.Dict`, `typing.Tuple`, `typing.Optional`, and `typing.Union`.
- Do not use assignment expressions (`:=`) unless the project explicitly raises the minimum Python version.
- Do not use `str.removeprefix()` or `str.removesuffix()`.
- Do not use `zoneinfo` without a compatibility dependency and a clear reason.
- Do not rely on `importlib.metadata` without the Python 3.7-compatible backport.
- Dataclasses are allowed; they are available in Python 3.7.
- Type hints must be valid at runtime on Python 3.7 unless a deliberate compatibility pattern is documented nearby.

## Published Standards We Follow

- **PEP 8** is the baseline for Python layout, naming, imports, and consistency.
- **PEP 20** is the readability and simplicity compass.
- **Google Python Style Guide** is the practical reference for large-codebase conventions.
- **Flask official patterns** guide application factories, blueprints, and larger application structure.
- **PEP 484** guides type hints, using Python 3.7-compatible syntax.
- **PEP 257** guides docstrings.
- **Diataxis** guides user and operator documentation.
- **OWASP-style review** applies to admin, auth, secrets, subprocess, filesystem, and network-facing changes.
- **RFC 9457 Problem Details** and **OpenAPI** are future targets for API error and schema consistency.

## Flask Architecture

Routes should stay thin. A route should parse HTTP input, call a service or helper, and return HTTP output.

Feature routes should move into blueprints as they are refactored. `setup_wizard.py` already uses this pattern, and new feature modules should follow it.

System behavior belongs outside route modules. Code that touches systemd, rclone, Samba, filesystems, SMTP, provider APIs, disks, or secrets should live behind a small service or adapter boundary.

Fake mode should be an alternate implementation behind those boundaries. Avoid scattering `runtime.is_fake` conditionals through unrelated route logic.

Shared response and validation helpers should be preferred over per-route ad hoc response shapes. Until a formal API schema pass happens, keep API responses predictable and use clear status codes.

Security work should follow the app's admin trust model. SimpleSaferServer is a root-run,
admin-only local management tool, so do not hide useful managed credentials or configuration from
administrators just for appearance. Avoid accidental spread instead: keep secrets out of logs,
broad status responses, process argv, unrelated UI, and overly broad filesystem permissions.

Avoid persistent writes unless the data must survive restart or is durable operator history/config.
Use volatile runtime state for status/cache data that can be rebuilt.

`docs/architecture.md` describes the current package architecture. New refactored code should move toward:

- `simple_safer_server/routes/` for Flask blueprints.
- `simple_safer_server/services/` for route-independent behavior.
- `simple_safer_server/adapters/` for system and fake-mode boundaries.
- `simple_safer_server/web/` for shared response and validation helpers.

Keep `__init__.py` files minimal. Put meaningful behavior in clearly named modules such as `services/task_service.py` or `routes/ddns.py`.

Do not add top-level Python modules for application runtime code. Put new route, service, adapter,
web helper, or legacy migration behavior inside the `simple_safer_server/` package.

## Python Style

- Prefer explicit names and small functions.
- Avoid mutable module-level state except for application composition and carefully documented runtime state.
- Avoid broad `except Exception` except at HTTP or script boundaries where the caller must receive a controlled response.
- Internal code should raise specific exceptions that routes can map to HTTP responses.
- Use dataclasses, enums, or typed objects when repeated dictionaries or string constants are becoming a contract.
- Prefer structured parsers and standard library APIs over ad hoc string manipulation when practical.
- Keep comments focused on operational surprises, hidden assumptions, and future-forgettable behavior.
- Do not write comments or docs that assume the reader knows a previous implementation. Describe the current behavior directly.

## Documentation Rules

Any behavior change should check the related docs and the documentation links in `index.html`.

User and operator behavior belongs in `docs/*.md`. Contributor-only rules belong here.

Chronological task notes belong in `notes/`. Notes are handoff history, not canonical
documentation; move durable behavior, commands, architecture, and workflow details into the
appropriate docs when they stop being task-specific.

When adding files, services, timers, state directories, generated artifacts, or system config, check whether `uninstall.sh` should remove them.

Remove standalone proof-of-concept scripts once their behavior is supported inside the app. If a
script is retained only for operator migration, document that status and avoid expanding it.

## Frontend Rules

Use the `frontend-design` and `uncodixfy` skills for UI work.

Reuse existing Bunker interface patterns and check `docs/internal_ui_patterns.md` before adding new UI behavior.

## Quality Commands

`requirements.txt` is the security-supported runtime dependency set and is validated on Debian 13
/ Python 3.13. `requirements-legacy-py37.txt` is a best-effort Debian 10 / Python 3.7 set for
compatibility testing only; it intentionally does not run strict dependency auditing because some
fixed package releases require newer Python versions. `requirements-dev.txt` uses environment
markers so each lane installs compatible development tools.

Install local development dependencies with:

```bash
bash install_dev.sh
```

Install the optional fast commit hooks with:

```bash
.venv/bin/pre-commit install
```

During normal development, run targeted tests for the code you changed. Before pushing or opening
a pull request, run the fast local check wrapper:

```bash
bash check_ci.sh
```

`check_ci.sh` runs the strict CI gates in your active `.venv`:

```bash
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest
.venv/bin/pyright
.venv/bin/python -m bandit -c pyproject.toml -r .
.venv/bin/python -m pip_audit -r requirements.txt -r requirements-dev.txt
```

When a change could depend on container behavior, or before pushing CI-sensitive changes, run both
GitHub Actions reproductions in Docker:

```bash
bash check_ci_docker.sh
```

`check_ci_docker.sh` runs the `python:3.13-trixie` security lane first, then the
`python:3.7-buster` compatibility lane. A green default Docker run should mean both CI workflow
lanes are green.

The pre-commit configuration intentionally stays lightweight and only runs ruff formatting/linting.
The full gate set is available through both check scripts.

Run a single lane when you need a faster focused check:

```bash
bash check_ci_docker.sh python313-security
bash check_ci_docker.sh python37-legacy-compat
```

`python37-legacy-compat` uses `python:3.7-buster`, installs `requirements-legacy-py37.txt`, and runs
formatting, linting, tests, pyright, bandit, and the Python 3.7 syntax parser. It skips pip-audit
because the fixed releases for Flask, Werkzeug, cryptography, NumPy, scikit-learn, python-socketio,
and related transitive packages require newer Python runtimes.

Local venv checks catch most gate failures, but GitHub Actions runs the strict security lane inside
`python:3.13-trixie` and the legacy compatibility lane inside `python:3.7-buster`. The syntax
compatibility check below is useful, but it does not catch Python 3.7 runtime behavior differences;
use `check_ci_docker.sh python37-legacy-compat` for that.

Check Python 3.7 syntax compatibility with:

```bash
python - <<'PY'
import ast
from pathlib import Path

for path in sorted(Path(".").rglob("*.py")):
    if any(part in {".venv", ".git", "__pycache__"} for part in path.parts):
        continue
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(path), feature_version=(3, 7))
PY
```

## Current Baseline Policy

Continuous integration currently runs advisory quality gates. A green `Python CI` workflow does
not imply full enforcement and may include advisory or continue-on-error behavior until the planned
cleanup/refactor pass removes advisory mode:

- `ruff format --check`
- `ruff check`
- `pytest`
- `pyright`
- `bandit`
- `pip-audit`

The `python37-legacy-compat` workflow job is compatibility-only. Keep it useful for Debian 10
operators, but do not add dependency-audit ignores to make old Python 3.7 packages appear
security-supported.

If repository branch protection uses required status checks, update those required check names
after workflow or job renames. The current workflow file is `.github/workflows/python-ci.yml`, with
jobs `python313-security` and `python37-legacy-compat`.

Bandit skips the generic subprocess import/execution rules because SimpleSaferServer is a local admin tool that intentionally calls Debian system utilities. Keep those subprocess calls behind services or adapters, validate user-controlled arguments before shelling out, and document operational assumptions near the code.
