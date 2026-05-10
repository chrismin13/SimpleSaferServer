# 0032 Install unattended-upgrades

## Summary

- Add `unattended-upgrades` to the baseline install package set so the System Updates automatic
  upgrade control has the apt backend it needs on fresh installs.

## Rules / Constraints

- Preserve Python 3.7 compatibility for Debian 10.
- Keep changes reviewable and avoid unrelated formatting churn.
- Check related docs, `index.html`, and `uninstall.sh`.
- Do not edit `README.md`.

## Target State

- Fresh automated and manual installs include `unattended-upgrades`.
- Documentation is clear that Debian and Ubuntu package defaults may already enable automatic
  security upgrades when the package is installed.

## Phase Checklist

- [x] Phase 1: Add package to installer and matching docs.
- [x] Phase 2: Verify shell syntax and focused tests.

## Work Log

### Phase 1

- Added `unattended-upgrades` to the `install.sh` apt package list.
- Updated `docs/manual_install.md` to match the automated installer package set.
- Updated `docs/system_updates.md` to explain that the backend is installed by default and that
  distro package defaults can affect initial automatic-upgrade state.

Docs and uninstall impact:

- `docs/manual_install.md` and `docs/system_updates.md` were updated.
- `index.html` links to the install and uninstall pages only; no link change was needed.
- `uninstall.sh` should not remove `unattended-upgrades` because it is a normal host security
  package and may have been installed or used independently of SimpleSaferServer.

Verification:

- `bash -n install.sh`: passed.
- `.venv/bin/python -m pytest tests/test_install_preflight.py tests/test_system_updates.py`:
  passed, 35 tests.

## Decisions

- Install the package even though distro defaults vary. The System Updates page already reads the
  current apt periodic values before adopting them, so administrators can see what the host is
  currently doing.

## Follow-Up Backlog

- None.
