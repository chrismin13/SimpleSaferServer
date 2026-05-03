# 0006 Review Feedback Verification

## Summary

- Verify each requested review finding against the current code and apply only the fixes still needed.
- Keep behavioral changes narrow while improving command timeouts, validation, encapsulation, and maintainer comments.

## Rules / Constraints

- Preserve Python 3.7 compatibility for Debian 10.
- Preserve behavior unless the current code confirms the reported bug or maintainability gap.
- Follow `docs/development.md` and keep comments focused on operational assumptions future maintainers may forget.
- Check related docs, `index.html`, and `uninstall.sh` for impact.

## Target State

- Contributor check instructions distinguish default pre-commit hooks from manual-stage hooks.
- System commands that can block have bounded timeouts where requested.
- Root-run services do not implicitly depend on `sudo`.
- SMTP port validation rejects non-numeric and out-of-range ports on both client and server paths.
- Route and service boundaries avoid private method access where public wrappers are appropriate.

## Phase Checklist

- [x] Phase 1: Verify current code and patch needed findings.
- [x] Phase 2: Run focused formatting and tests.

## Work Log

### Phase 1

- Started from a clean worktree and confirmed the requested comments are not already fully addressed.
- Patched the confirmed findings around pre-commit instructions, bounded systemctl calls, no-sudo SMB commands, SMTP port validation, public service/user-manager methods, comments, and tests.
- Ran `ruff format .`; `backup_drive_setup.py` changed only by formatter-driven line wrapping.

Docs and uninstall impact:

- README and `docs/development.md` now document manual-stage pre-commit hooks.
- `docs/alerts.md` and `docs/setup.md` now describe SMTP ports as TCP ports in the 1-65535 range.
- `index.html` already links to the related docs. `uninstall.sh` needs no change because no installed files, services, timers, state directories, or generated system config were added.

Verification:

- `.venv/bin/python -m ruff format .`
- `.venv/bin/python -m ruff check .`
- `.venv/bin/python -m pytest`

## Decisions

- Treat CI formatting for `backup_drive_setup.py` as formatter-only unless ruff reports additional required changes.

## Follow-Up Backlog

- None yet.
