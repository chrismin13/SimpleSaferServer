# 0004 Legacy Artifact Cleanup

## Summary

- Remove standalone artifacts that are not part of supported SimpleSaferServer runtime behavior.
- Migrate app startup to package entrypoints so top-level `app.py` can be removed.

## Rules / Constraints

- Preserve Python 3.7 compatibility for Debian 10.
- Preserve user-facing behavior for active app features.
- Check related docs, `index.html`, and `uninstall.sh`.

## Target State

- Runtime startup uses `python -m simple_safer_server`.
- Hosted WSGI startup uses `simple_safer_server.wsgi:app`.
- Dead proof-of-concept/helper files are gone from install and uninstall paths.

## Phase Checklist

- [x] Phase 1: Audit candidate legacy files and classify active runtime code versus removable artifacts.
- [x] Phase 2: Remove confirmed dead standalone files and references.
- [x] Phase 3: Replace top-level app startup with package entrypoints.
- [x] Phase 4: Update docs and uninstall/install references.
- [x] Phase 5: Run quality gates and entrypoint smoke checks.

## Work Log

### Phase 1

- Confirmed `backup_to_mega.py`, `setup.sh`, `update_scripts.sh`, and `scripts/predict_health.py` have no supported callers.
- Confirmed `scripts/predict_health.py` is obsolete because `drive_health.py` loads the model directly.
- Confirmed `legacy_migration.py` and `scripts/import_legacy.py` are retained as deprecated operator migration tooling.
- Confirmed active top-level modules such as `backup_drive_setup.py`, `drive_health.py`, and `system_updates.py` are not dead code.

Docs and uninstall impact:

- `uninstall.sh` no longer removes `predict_health.py` because the script is no longer installed.
- `docs/architecture.md`, `docs/manual_install.md`, and `docs/development.md` record the package entrypoint and legacy cleanup policy.
- `index.html` links did not need changes because no docs were renamed or added to the public index.

Verification:

- Python 3.7 syntax compatibility check passed.
- `ruff format --check .` passed.
- `ruff check .` passed.
- `pytest` passed locally on Python 3.14 with 163 tests and one existing `datetime.utcnow()` deprecation warning.
- `pyright` passed with 0 errors and 0 warnings.
- Bandit passed with no issues.
- `pip-audit` passed with no known vulnerabilities.
- Fake-mode package startup smoke check reached the Flask dev server before the timeout stopped it.
- Fake-mode Gunicorn config check for `simple_safer_server.wsgi:app` passed.

## Decisions

- Remove `app.py` now and make package entrypoints canonical.
- Keep legacy import, but treat it as deprecated and avoid new feature investment.

## Follow-Up Backlog

- Migrate active top-level runtime modules into package modules in separate behavior-preserving slices.
- Decide whether the deprecated legacy import path needs a formal removal version or support window.
