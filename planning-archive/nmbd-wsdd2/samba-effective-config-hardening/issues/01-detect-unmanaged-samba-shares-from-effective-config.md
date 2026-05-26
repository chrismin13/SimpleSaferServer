# Detect Unmanaged Samba Shares From Effective Config

## What to build

Create the shared inspection path for Unmanaged Samba Shares. The completed slice should ask Samba
to parse a stripped candidate config instead of scanning the main Samba config text directly. The
candidate should remove only SimpleSaferServer-owned include blocks, live under the volatile runtime
directory, be checked with `testparm`, and produce non-system share names that callers can use for
warnings and write-safety decisions.

## Acceptance criteria

- [ ] Unmanaged Samba Share inspection removes the SimpleSaferServer global include block from the candidate config.
- [ ] Unmanaged Samba Share inspection removes the SimpleSaferServer shares include block from the candidate config.
- [ ] The stripped candidate config is written under the runtime volatile directory.
- [ ] Real-mode write-safety inspection does not fall back to `/tmp` when the volatile runtime directory is unavailable.
- [ ] The candidate config is deleted after inspection.
- [ ] Inspection runs `testparm -s` or the existing adapter's equivalent effective-config command against the stripped candidate.
- [ ] Inspection parses non-system share section names from Samba's effective output.
- [ ] Shares from non-SimpleSaferServer include files are detected.
- [ ] System sections such as `global`, `homes`, `printers`, and `print$` are not reported as Unmanaged Samba Shares.
- [ ] Malformed SimpleSaferServer include marker blocks fail closed.
- [ ] `testparm` failure or unavailable effective-config inspection fails closed for write-safety callers.
- [ ] Focused tests cover volatile temp placement, marker stripping, included unmanaged shares, system-section filtering, malformed markers, command failure, and cleanup.
- [ ] `README.md` is not modified.

## Blocked by

None - can start immediately.
