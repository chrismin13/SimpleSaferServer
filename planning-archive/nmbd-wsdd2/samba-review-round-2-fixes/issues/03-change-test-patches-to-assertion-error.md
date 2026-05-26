# Change test patches to AssertionError for effective-config inspection guards

## Parent

Planning/samba-review-round-2-fixes/PRD.md

## What to build

Two tests patch `_inspect_unmanaged_effective_shares` with `SMBConfigError` to prove that managed
share user reads/updates do not depend on effective config inspection. However, the patched method
is never called in those code paths (the share is found in the managed file first), so the patch is
dead — the tests pass identically without it.

Change both patches to use `AssertionError` side effects, matching the pattern already used by
`test_delete_managed_share_does_not_inspect_unmanaged_effective_config`. This makes the intent
explicit ("this must NOT be called") and catches regressions if someone accidentally adds an
inspection call to those paths.

Tests to change:

- `test_get_share_users_succeeds_when_effective_config_inspection_fails`
- `test_update_share_users_succeeds_when_effective_config_inspection_fails`

## Acceptance criteria

- [ ] Both tests use `side_effect=AssertionError("should not inspect effective config for a managed share")` instead of `side_effect=smb_manager.SMBConfigError("broken include")`.
- [ ] Both tests still pass.
- [ ] Test names updated to reflect the guard intent (e.g., `test_get_share_users_does_not_inspect_effective_config_for_managed_share`).

## Blocked by

None - can start immediately.
