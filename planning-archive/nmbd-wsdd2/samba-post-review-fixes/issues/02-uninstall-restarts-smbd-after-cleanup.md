# Uninstall restarts smbd after successful Samba cleanup

## Parent

Planning/samba-post-review-fixes/PRD.md

## What to build

After `cleanup_managed_smb_shares` successfully rewrites `smb.conf` (include blocks stripped) and
deletes the owned include files, restart `smbd` so the running service matches the on-disk config.
The restart is best-effort: warn and continue if it fails.

Because the restart interrupts active file transfers, add a warning to the top-level uninstall
confirmation prompt: "Active Samba file transfers will be interrupted."

Update `docs/uninstall.md` and the `index.html` uninstall section to mention that Samba is
restarted and active transfers will be dropped.

Discovery services (`nmbd`, `wsdd2`) are NOT restarted — they are shared system services and the
uninstaller leaves them running.

## Acceptance criteria

- [ ] Successful `cleanup_managed_smb_shares` calls `systemctl restart smbd` after rewriting `smb.conf` and deleting owned files.
- [ ] If `smbd` restart fails, a warning is printed but the function does not return failure.
- [ ] The top-level uninstall confirmation prompt includes a line about active Samba file transfers being interrupted.
- [ ] `docs/uninstall.md` mentions the `smbd` restart and transfer interruption.
- [ ] `index.html` uninstall note mentions the `smbd` restart and transfer interruption.
- [ ] `nmbd` and `wsdd2` are NOT restarted by the uninstall script.
- [ ] Existing uninstall tests pass; new tests cover the restart and warning behavior.

## Blocked by

None - can start immediately.
