# Clean Owned Samba Files On Uninstall Independently

## What to build

Split uninstall's main Samba config rewrite from deletion of SimpleSaferServer-owned Samba files.
When the main Samba config exists, uninstall should remove SimpleSaferServer include blocks without
touching unrelated config. Whether or not the main config exists, uninstall should delete the owned
globals and shares files. Malformed include marker blocks should still prevent unsafe rewrites of
the main config.

## Acceptance criteria

- [ ] If the main Samba config exists, uninstall removes the SimpleSaferServer global include block.
- [ ] If the main Samba config exists, uninstall removes the SimpleSaferServer shares include block.
- [ ] If the main Samba config is missing, uninstall skips only the main-config rewrite.
- [ ] Uninstall deletes the SimpleSaferServer-owned globals file even when the main Samba config is missing.
- [ ] Uninstall deletes the SimpleSaferServer-owned shares file even when the main Samba config is missing.
- [ ] Malformed SimpleSaferServer include marker blocks prevent rewriting the main Samba config.
- [ ] Malformed main-config markers do not prevent deleting unambiguously owned SimpleSaferServer Samba files.
- [ ] Uninstall leaves unmanaged shares, unrelated include lines, shared packages, and non-SSS service state alone.
- [ ] Final uninstall messaging remains accurate.
- [ ] Focused uninstall tests cover missing main config, owned-file deletion, normal include removal, malformed marker rejection, and unrelated config preservation.
- [ ] `README.md` is not modified.

## Blocked by

None - can start immediately.
