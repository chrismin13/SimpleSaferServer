# Treat "unavailable" as non-degrading in overall status logic

## Parent

Planning/samba-review-round-2-fixes/PRD.md

## What to build

The dashboard and network file sharing page both determine an overall Samba status (Operational /
Partial / Down). Currently, any non-`active` state for `nmbd` or `wsdd2` triggers "Partial." On
systems where wsdd2 is not packaged, the status API returns `"unavailable"`, causing a permanent
yellow badge even though the system is operating as well as it can.

Change the overall status logic on both pages so that `"unavailable"` is treated as non-degrading:

- **Operational:** smbd active AND nmbd is active-or-unavailable AND wsdd2 is active-or-unavailable
- **Partial:** smbd active but at least one discovery service is `inactive` or `error` (not `unavailable`)
- **Down:** smbd not active

The per-service badges on the network file sharing page remain unchanged — `discoveryBadgeClass`
still shows grey/neutral for `"unavailable"`, yellow for `"inactive"`, green for `"active"`.

Update the existing integration tests that assert on the rendered page's status logic to confirm the
new unavailable-aware conditions are present.

## Acceptance criteria

- [ ] Dashboard shows "Operational" when smbd=active, nmbd=active, wsdd2=unavailable.
- [ ] Dashboard shows "Partial" when smbd=active, nmbd=inactive, wsdd2=active.
- [ ] Dashboard shows "Down" when smbd=inactive.
- [ ] Network file sharing page overall status follows the same three rules.
- [ ] Per-service badges on the file sharing page are unchanged (grey for unavailable).
- [ ] `test_dashboard_file_sharing_summary_tracks_wsdd2_and_three_state_rules` updated and passes.
- [ ] `test_discovery_badges_use_three_tier_and_smbd_stays_binary` updated and passes.
- [ ] Documentation in `docs/network_file_sharing.md` and `docs/dashboard.md` updated to reflect
      that "unavailable" discovery services do not degrade the overall status.

## Blocked by

None - can start immediately.
