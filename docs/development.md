# Development & Coding Conventions

This document is the source of truth for how SimpleSaferServer code should be written, reviewed, and refactored.

New code should follow these conventions immediately. Existing code should move toward them when it is touched or during planned refactors, without unrelated formatting churn.

## Compatibility Target

SimpleSaferServer supports Python 3.7+ because Debian 10 ships Python 3.7.

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

`docs/architecture.md` describes the current package architecture. New refactored code should move toward:

- `simple_safer_server/routes/` for Flask blueprints.
- `simple_safer_server/services/` for route-independent behavior.
- `simple_safer_server/adapters/` for system and fake-mode boundaries.
- `simple_safer_server/web/` for shared response and validation helpers.

Keep `__init__.py` files minimal. Put meaningful behavior in clearly named modules such as `services/task_service.py` or `routes/ddns.py`.

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

`requirements-dev.txt` uses environment markers so Debian 10/Python 3.7 installs compatible older tool versions, while newer development machines receive newer tool versions where old releases no longer run cleanly.

Install local development dependencies with:

```bash
bash install_dev.sh
```

Install commit hooks with:

```bash
.venv/bin/pre-commit install
```

Run the standard checks with:

```bash
.venv/bin/python -m ruff format .
.venv/bin/python -m ruff check . --fix
.venv/bin/python -m pytest
.venv/bin/pyright
.venv/bin/python -m bandit -c pyproject.toml -r .
.venv/bin/python -m pip_audit -r requirements.txt -r requirements-dev.txt --ignore-vuln GHSA-6w46-j5rx-g56g
.venv/bin/pre-commit run --all-files
```

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

Continuous integration runs the standard checks as strict gates:

- `ruff format --check`
- `ruff check`
- `pytest`
- `pyright`
- `bandit`
- `pip-audit`

Bandit skips the generic subprocess import/execution rules because SimpleSaferServer is a local admin tool that intentionally calls Debian system utilities. Keep those subprocess calls behind services or adapters, validate user-controlled arguments before shelling out, and document operational assumptions near the code.

The dependency audit currently ignores `GHSA-6w46-j5rx-g56g` for `pytest==7.4.4`. The fixed pytest release requires a newer Python than Debian 10 provides, and this dependency is development-only. Remove that ignore when the project raises its minimum Python version.
