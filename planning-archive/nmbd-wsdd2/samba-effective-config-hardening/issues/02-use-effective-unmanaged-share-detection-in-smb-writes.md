# Use Effective Unmanaged-Share Detection In SMB Writes

## What to build

Wire include-aware Unmanaged Samba Share detection into the SMB write paths. Creating a
SimpleSaferServer-Managed Share, renaming one, and setup's default `backup` share creation should
reject names that already exist as Unmanaged Samba Shares in Samba's Effective Samba Config. Owned
share listing and editing should continue using the SimpleSaferServer-owned shares file as the
ownership boundary.

## Acceptance criteria

- [ ] Managed share listing still reads SimpleSaferServer-Managed Shares from the owned shares file.
- [ ] Creating a SimpleSaferServer-Managed Share rejects a target name found by effective Unmanaged Samba Share inspection.
- [ ] Renaming a SimpleSaferServer-Managed Share rejects a new name found by effective Unmanaged Samba Share inspection.
- [ ] Setup default `backup` share creation rejects unmanaged `backup` from effective Unmanaged Samba Share inspection.
- [ ] Updating an existing SimpleSaferServer-Managed Share without renaming does not treat itself as unmanaged.
- [ ] Deleting a SimpleSaferServer-Managed Share does not require an unmanaged-share conflict check.
- [ ] Effective-config inspection failures fail create, rename, and setup default-share writes with controlled API-visible errors.
- [ ] Existing short setup conflict text is preserved for unmanaged `backup`: `Samba share "backup" already exists. Rename or remove it, then retry.`
- [ ] Focused tests cover create conflict, rename conflict, setup `backup` conflict, no-rename update, delete behavior, and inspection failure.
- [ ] `README.md` is not modified.

## Blocked by

- Issue 1 - Detect Unmanaged Samba Shares From Effective Config.
