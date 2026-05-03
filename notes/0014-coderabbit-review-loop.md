# CodeRabbit Review Loop

## Context

This note tracks the branch review against `main` using the CodeRabbit CLI. The branch contains a
large package refactor plus installer, documentation, CI, and UI work, so review feedback should be
handled structurally rather than as one-off patches where a broader code pattern is responsible.

## Review Rounds

- Started a CodeRabbit agent review against `main` with repository instructions included from
  `AGENTS.md`.
- First review completed with 13 findings. Verified and fixed all findings:
  os-release quote normalization, unknown distro response shape, root debug warning, apt cleanup
  guard/reaping, drive-health refresh error ordering, storage UUID defaults, installer fixture
  dedenting, user timestamp handling, and Samba-first password persistence.
- Follow-up inline comments were checked against the current tree before editing. Confirmed fixes
  include the manual install service/Gunicorn distinction, drive-health upgrade notice publishing,
  apt conflict typing, dashboard mount probing, MEGA config persistence ordering, Samba UTF-8 file
  I/O, stable storage errors, append-only system update logs, user password persistence ordering,
  stale UI state cleanup, legacy import diagnostics, alert write locking, and requested comments.

## Decisions

- Keep review fixes aligned with `docs/development.md`: route code stays thin, subprocess behavior
  remains behind service or adapter boundaries, and Python application code remains compatible with
  Python 3.7 syntax.
- Treat legacy user timestamps without an offset as UTC so existing `users.json` lockout state
  remains comparable after current code starts writing timezone-aware values.
- Store system update output in a separate append-only volatile log file while keeping compact
  operation metadata in JSON. This avoids repeated full JSON rewrites during noisy apt runs while
  preserving the existing `get_status()["log"]` response contract.

## Verification

- `.venv/bin/python -m pytest tests/test_user_manager.py tests/test_os_support.py tests/test_runtime_command_adapters.py tests/test_install_preflight.py tests/test_storage_service.py tests/test_app_factory_routes.py`
- `.venv/bin/python -m ruff format --check simple_safer_server/services/os_support.py simple_safer_server/__main__.py simple_safer_server/adapters/system_updates_commands.py simple_safer_server/services/user_manager.py simple_safer_server/routes/storage.py tests/test_install_preflight.py tests/test_user_manager.py tests/test_os_support.py tests/test_runtime_command_adapters.py`
- `.venv/bin/python -m ruff check simple_safer_server/services/os_support.py simple_safer_server/__main__.py simple_safer_server/adapters/system_updates_commands.py simple_safer_server/services/user_manager.py simple_safer_server/routes/storage.py tests/test_install_preflight.py tests/test_user_manager.py tests/test_os_support.py tests/test_runtime_command_adapters.py`
