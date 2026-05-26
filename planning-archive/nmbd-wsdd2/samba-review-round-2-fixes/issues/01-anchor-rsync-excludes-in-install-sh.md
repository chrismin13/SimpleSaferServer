# Anchor rsync excludes in install.sh

## Parent

Planning/samba-review-round-2-fixes/PRD.md

## What to build

The installer's main rsync command uses `--exclude='templates'` and `--exclude='static'` which
match at any directory depth. This excludes `simple_safer_server/services/templates/` (containing
the Samba globals config template) from deployment, causing `SambaLayoutService.ensure_layout()` to
fail with `FileNotFoundError` at install step 9.

Anchor both excludes to the rsync source root so only the top-level `templates/` and `static/`
directories are excluded (they are copied separately in step 5). Nested directories with those
names inside the Python package must be deployed with the main app copy.

## Acceptance criteria

- [ ] `--exclude='templates'` changed to `--exclude='/templates'` in the main rsync command.
- [ ] `--exclude='static'` changed to `--exclude='/static'` in the main rsync command.
- [ ] `simple_safer_server/services/templates/simple_safer_server_globals.conf` would be included in the rsync destination.
- [ ] All existing install preflight tests pass.
- [ ] All existing samba layout tests pass.

## Blocked by

None - can start immediately.
