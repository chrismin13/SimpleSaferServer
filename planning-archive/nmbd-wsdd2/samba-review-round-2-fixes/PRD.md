# Samba Review Round 2 Fixes PRD

## Problem Statement

A second code review of the uncommitted Samba redesign changeset found three remaining issues:

1. **Installer rsync excludes `simple_safer_server/services/templates/`** — the `--exclude='templates'`
   pattern matches at any depth, so the globals config template file is never deployed to
   `/opt/SimpleSaferServer`. The installer's step 9 (`SambaLayoutService.ensure_layout()`) will fail
   with `FileNotFoundError`, blocking installation entirely.

2. **Dashboard and file sharing page show "Partial/Degraded" when wsdd2 is unavailable** — the
   overall status logic treats any non-`active` state as degradation. On systems where wsdd2 was
   never installed (package unavailable on the distro), the status API returns `"unavailable"`,
   causing a permanent yellow badge. The semantic distinction is: `"unavailable"` means "never
   installed / not applicable" while `"inactive"` means "installed but stopped." Only the latter is
   degradation.

3. **Two test patches are dead code** — `test_get_share_users_succeeds_when_effective_config_inspection_fails`
   and `test_update_share_users_succeeds_when_effective_config_inspection_fails` patch
   `_inspect_unmanaged_effective_shares` with `SMBConfigError`, but the code path never calls that
   method (the share is found in the managed file, so inspection is skipped). The tests pass
   identically without the patch.

## Solution

1. Anchor the rsync excludes in `install.sh` so only top-level `templates/` and `static/` are
   excluded from the main app copy.

2. Change the overall status logic on both the dashboard and the network file sharing page to treat
   `"unavailable"` as non-degrading. Per-service badges on the file sharing page remain unchanged
   (grey neutral for unavailable).

3. Change the two test patches to use `AssertionError` side effects (matching the pattern already
   used by `test_delete_managed_share_does_not_inspect_unmanaged_effective_config`) so they catch
   regressions if someone accidentally adds an inspection call to those paths.

## User Stories

1. As an administrator running the installer, I want the Samba globals template file deployed correctly, so that `SambaLayoutService.ensure_layout()` succeeds and installation completes.
2. As an administrator on a system without wsdd2, I want the dashboard to show "Operational" when smbd is active and discovery services are either active or not applicable, so that I am not alarmed by a permanent yellow badge for a package my distro does not provide.
3. As an administrator on a system where wsdd2 is installed but stopped, I want the dashboard to show "Partial" so that I know a service that should be running is down.
4. As an administrator viewing the network file sharing page, I want the overall status banner to follow the same operational/partial/down rules as the dashboard, so that the two pages agree.
5. As an administrator viewing the network file sharing page, I want to see the individual wsdd2 badge as grey "unavailable" when the package is not installed, so that I know the service is absent rather than broken.
6. As a future maintainer, I want the test patches on `get_share_users` and `update_share_users` to use `AssertionError` so that a regression adding unnecessary effective-config inspection is caught immediately.

## Implementation Decisions

- In `install.sh` line 558, change `--exclude='templates'` to `--exclude='/templates'` and
  `--exclude='static'` to `--exclude='/static'`. The leading `/` anchors the pattern to the rsync
  source root, so nested directories with the same name are no longer excluded.
- In `templates/dashboard.html`, extract a helper (or inline condition) that treats both `'active'`
  and `'unavailable'` as non-degrading for the overall status check. The three states become:
  - Operational: smbd active AND nmbd is active-or-unavailable AND wsdd2 is active-or-unavailable
  - Partial: smbd active but at least one discovery service is inactive (not unavailable)
  - Down: smbd not active
- In `templates/network_file_sharing.html`, apply the same overall status logic to the
  `updateOverallStatus` call inside `loadSMBStatus()`.
- The `discoveryBadgeClass` function and per-service badge rendering remain unchanged.
- In `tests/test_smb_manager.py`, change the `side_effect` in
  `test_get_share_users_succeeds_when_effective_config_inspection_fails` and
  `test_update_share_users_succeeds_when_effective_config_inspection_fails` from
  `smb_manager.SMBConfigError("broken include")` to
  `AssertionError("should not inspect effective config for a managed share")`.

## Testing Decisions

Good tests verify observable behavior. The rsync fix is best verified by the existing
`test_samba_layout_helper_invoked_without_creating_backup_share` install preflight test (which
exercises the installer text) and by the `test_samba_layout.py` tests that exercise the template
read. The dashboard/file-sharing status logic is client-side JavaScript tested by the existing
`test_discovery_badges_use_three_tier_and_smbd_stays_binary` and
`test_dashboard_file_sharing_summary_tracks_wsdd2_and_three_state_rules` integration tests, which
should be updated to assert the new unavailable-is-not-degrading semantics.

Modules to verify:

- `install.sh`: confirm the rsync exclude anchoring does not break the existing preflight tests.
- `templates/dashboard.html`: update
  `test_dashboard_file_sharing_summary_tracks_wsdd2_and_three_state_rules` to assert the
  unavailable-aware condition is present in the rendered page.
- `templates/network_file_sharing.html`: update or add assertions in
  `test_discovery_badges_use_three_tier_and_smbd_stays_binary` to confirm the overall status logic
  treats unavailable as non-degrading.
- `tests/test_smb_manager.py`: the two patched tests should still pass after changing to
  `AssertionError`.

Prior art:

- `test_delete_managed_share_does_not_inspect_unmanaged_effective_config` already uses the
  `AssertionError` pattern for the same purpose.
- `tests/test_install_preflight.py` tests installer script text content.
- `tests/test_app_factory_routes.py` tests rendered page content for status logic.

## Out of Scope

- Migration of old marker-wrapped shares (no existing installations to upgrade).
- Global include placement inside old marker blocks (non-issue for fresh installs).
- Changes to the Samba ownership model or layout helper behavior.
- Changes to `README.md`.

## Further Notes

The rsync fix is a hard blocker — without it, no fresh installation can complete. The status logic
fix is a UX improvement that prevents false alarms on systems where wsdd2 is simply not packaged.
The test fix is housekeeping that makes intent explicit and catches future regressions.
