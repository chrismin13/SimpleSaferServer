# Honor Required smbd Failure In Installer

## What to build

Make the installer honor required Samba file-serving failure. The top-level installer should stop
when Samba service setup reports that `smbd` is not active after setup. It should still distinguish
that hard failure from loud warnings where `smbd` is active now but enable/start commands returned
nonzero and reboot persistence may need administrator attention.

## Acceptance criteria

- [ ] The top-level installer checks the Samba service setup function's return value.
- [ ] The installer exits nonzero when `smbd` is not active after Samba service setup.
- [ ] `smbd` active state is the hard requirement for install success.
- [ ] Failed `smbd` enable with final active state `active` prints a loud warning and continues.
- [ ] Failed `smbd` start with final active state `active` prints a loud warning and continues.
- [ ] Required `smbd` failure output includes actionable remediation guidance.
- [ ] `nmbd` and `wsdd2` enable/start/status failures remain non-fatal and appear as warnings or summary state.
- [ ] Focused shell/static tests cover top-level return handling, inactive `smbd`, active-with-enable-warning, active-with-start-warning, and best-effort discovery failures.
- [ ] `README.md` is not modified.

## Blocked by

None - can start immediately.
