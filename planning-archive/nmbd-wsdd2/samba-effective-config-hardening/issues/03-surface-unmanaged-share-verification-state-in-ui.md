# Surface Unmanaged-Share Verification State In The UI

## What to build

Update the Network File Sharing share-list path so the page's unmanaged-share warning uses the same
Effective Samba Config inspection as write safety. If inspection cannot verify Unmanaged Samba
Shares on a read/page-load path, the UI should show a controlled warning state instead of silently
reporting zero unmanaged shares.

## Acceptance criteria

- [ ] The share-list API uses effective Unmanaged Samba Share inspection for unmanaged-share warning data.
- [ ] The share-list API response can represent an unmanaged-share verification failure without pretending no unmanaged shares exist.
- [ ] The Network File Sharing page displays a visible warning/error state when unmanaged shares cannot be verified.
- [ ] The existing unmanaged-share modal still lists detected Unmanaged Samba Share names when verification succeeds.
- [ ] The UI reuses existing Bunker warning/toast/modal patterns and does not add a large explanatory panel.
- [ ] Existing managed-share table behavior remains unchanged when unmanaged-share verification succeeds.
- [ ] Focused API and rendering tests cover detected unmanaged shares, no unmanaged shares, and verification failure.
- [ ] Related Network File Sharing docs are updated if the visible verification state changes operator behavior.
- [ ] `README.md` is not modified.

## Blocked by

- Issue 1 - Detect Unmanaged Samba Shares From Effective Config.
