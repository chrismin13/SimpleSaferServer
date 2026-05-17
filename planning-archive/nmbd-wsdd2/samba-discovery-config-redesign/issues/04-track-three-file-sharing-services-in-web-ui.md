# Track Three File-Sharing Services In The Web UI

## What to build

Extend the file-sharing status and restart experience from two services to three: `smbd`, `nmbd`,
and `wsdd2`.

The completed slice should update the flat status API, restart behavior, Network File Sharing page,
and Dashboard summary. It should label the services by purpose, keep explanations lightweight, and
use the agreed operational rules: all three active is operational, `smbd` active with incomplete
discovery is partial, and `smbd` inactive is down.

## Acceptance criteria

- [ ] The service status API returns a flat object containing `smbd`, `nmbd`, and `wsdd2`.
- [ ] Missing `wsdd2` unit/service is reported as `unavailable`.
- [ ] Existing `smbd` and `nmbd` status behavior remains compatible with current callers after the new field is added.
- [ ] The restart API attempts to restart `smbd`, `nmbd`, and `wsdd2`.
- [ ] The restart API fails when `smbd` restart fails.
- [ ] `nmbd` or `wsdd2` restart failure does not trigger share rollback; status polling can show the partial state.
- [ ] The Network File Sharing page shows `SMB Daemon (smbd)`.
- [ ] The Network File Sharing page shows `NetBIOS Discovery (nmbd)`.
- [ ] The Network File Sharing page shows `Windows Discovery (wsdd2)`.
- [ ] The `smbd` hover/help text says it serves file shares.
- [ ] The `nmbd` hover/help text says it helps older Windows network browsing find this server.
- [ ] The `wsdd2` hover/help text says it helps modern Windows network browsing find this server.
- [ ] Network File Sharing overall status is `Operational` only when all three services are active.
- [ ] Network File Sharing overall status is `Partial` when `smbd` is active and `nmbd` or `wsdd2` is inactive/unavailable.
- [ ] Network File Sharing overall status is `Down` when `smbd` is inactive.
- [ ] Dashboard file-sharing summary includes `wsdd2` in its detail text.
- [ ] Dashboard file-sharing summary uses the same operational/partial/down rules as the Network File Sharing page.
- [ ] UI changes reuse existing Bunker service-status patterns and avoid a new explanation panel.
- [ ] Focused API, service, and UI rendering tests cover all-three active, discovery partial, missing `wsdd2`, and `smbd` down cases.
- [ ] `README.md` is not modified.

## Blocked by

- Issue 2 - Move managed shares to the SSS shares file.
- Issue 3 - Install and report discovery services.
