# Livepatch Uninstall Warning

## Context

SimpleSaferServer can set up Ubuntu Livepatch through Ubuntu Pro. Uninstall should inform admins
when the app performed that setup, but it should not detach Ubuntu Pro or disable Livepatch because
those are host-level subscription and security decisions.

## Changes

- Added `system_updates.livepatch_managed = true` after successful real Livepatch setup.
- Added `livepatch_was_managed()` to `uninstall.sh` so the final uninstall output can warn only
  when the marker exists.
- Documented that Ubuntu Pro and Livepatch state survive uninstall and require manual review.

## Docs and Uninstall Impact

- Updated `docs/system_updates.md` and `README.md`.
- Checked `index.html`: it already links to the System Updates docs, so no link change was needed.
- `uninstall.sh` now reads the marker before removing `/etc/SimpleSaferServer` and leaves Ubuntu
  Pro and Livepatch state untouched.

## Verification

- Passed: `pytest tests/test_system_updates.py tests/test_uninstall.py`
- Passed: `ruff check simple_safer_server/services/system_updates.py tests/test_system_updates.py tests/test_uninstall.py`
