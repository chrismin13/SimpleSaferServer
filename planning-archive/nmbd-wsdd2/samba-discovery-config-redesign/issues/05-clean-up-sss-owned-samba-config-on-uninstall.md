# Clean Up SSS-Owned Samba Config On Uninstall

## What to build

Update uninstall behavior for the new Samba ownership model.

The completed slice should remove only SimpleSaferServer-owned Samba include blocks and owned Samba
files. It should leave unmanaged Samba config, shared packages, and non-SSS service state alone.

## Acceptance criteria

- [ ] Uninstall removes the SSS global include block from the main Samba config.
- [ ] Uninstall removes the SSS shares include block from the main Samba config.
- [ ] Uninstall deletes the SSS globals file.
- [ ] Uninstall deletes the SSS shares file.
- [ ] Uninstall leaves unrelated include lines in the main Samba config untouched.
- [ ] Uninstall leaves unmanaged Samba share blocks untouched.
- [ ] Uninstall leaves Samba packages installed.
- [ ] Uninstall leaves `wsdd2` installed if present.
- [ ] Uninstall does not blindly disable `wsdd2.service`.
- [ ] Uninstall continues removing SimpleSaferServer-created Samba users according to existing user cleanup behavior.
- [ ] Uninstall final messaging mentions that SSS-owned Samba include files were removed.
- [ ] Uninstall final messaging mentions that shared packages/services such as Samba and `wsdd2` are left installed.
- [ ] Malformed SSS include marker blocks fail closed instead of rewriting `smb.conf` dangerously.
- [ ] Focused uninstall tests cover include block removal, owned file deletion, unrelated include preservation, unmanaged share preservation, malformed marker rejection, and final messaging.
- [ ] `README.md` is not modified.

## Blocked by

- Issue 1 - Establish SSS-owned Samba layout.
