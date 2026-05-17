# Uninstall warns about broken includes when marker stripping fails

## Parent

Planning/samba-post-review-fixes/PRD.md

## What to build

When the Python marker-stripping script fails (malformed SimpleSaferServer include markers in
`smb.conf`), the uninstall already deletes the owned include files and returns failure. Add a loud,
actionable warning that tells the administrator exactly what to do:

The warning should explain that `smb.conf` still contains `include` lines referencing the deleted
files, name both files (`simple_safer_server_globals.conf` and `simple_safer_server_shares.conf`),
and give the exact recovery command (`systemctl restart smbd`).

This does NOT change the decision to delete owned files on failure — that behavior stays. The fix
is purely about giving the admin a clear recovery path instead of silently leaving Samba in a
broken state.

## Acceptance criteria

- [ ] When marker stripping fails, the uninstall prints a warning naming both deleted files and telling the admin to remove the referencing `include` lines from `smb.conf`.
- [ ] The warning includes `systemctl restart smbd` as the final recovery step.
- [ ] The owned files are still deleted (existing behavior preserved).
- [ ] The function still returns failure (existing behavior preserved).
- [ ] A test verifies the warning text appears in stdout when markers are malformed.

## Blocked by

None - can start immediately.
