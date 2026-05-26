# Move Managed Shares To The SSS Shares File

## What to build

Move SimpleSaferServer-managed share behavior onto the SSS-owned shares file. A managed share is any
share section in the SSS shares file. Comments may remain for human readability, but normal app code
must not use share marker comments as the ownership boundary.

The completed slice should make share listing, creation, update, deletion, and setup's default
`backup` share use the SSS shares file. It should reject unsafe name conflicts with non-SSS Samba
shares and keep the setup retry experience short and clear.

## Acceptance criteria

- [ ] Managed share listing reads shares from the SSS shares file.
- [ ] Managed share creation writes new share sections to the SSS shares file.
- [ ] Managed share update rewrites the selected share in the SSS shares file.
- [ ] Managed share deletion removes the selected share from the SSS shares file.
- [ ] Normal app behavior no longer treats marker comments in the main Samba config as managed-share ownership.
- [ ] Before creating a new managed share, the app rejects the operation if that share name exists outside the SSS shares file.
- [ ] Before renaming a managed share, the app rejects the operation if the new name exists outside the SSS shares file.
- [ ] Conflict detection respects non-SSS includes where practical by using Samba's effective config or another equally safe effective-config check.
- [ ] If conflict detection cannot prove safety, the operation is rejected instead of relying on include precedence.
- [ ] Setup completion creates or updates the default `backup` share only after the configured mount point is known.
- [ ] If an unmanaged `backup` share already exists, setup completion returns the short retryable message: `Samba share "backup" already exists. Rename or remove it, then retry.`
- [ ] A failed unmanaged `backup` conflict does not clear persisted setup values.
- [ ] Manual unsupported directives in the SSS shares file do not crash share listing or supported-field display.
- [ ] Editing a share through the Web UI may rewrite that share in the supported SSS format and drop unsupported directives.
- [ ] Structurally malformed SSS shares file content returns a clear API error instead of crashing.
- [ ] Share writes ensure the SSS layout exists before editing the shares file.
- [ ] Share writes validate the effective Samba config before publish.
- [ ] Share writes roll back when validation fails or required `smbd` restart fails.
- [ ] Focused tests cover SSS-file list/create/update/delete, unmanaged conflict rejection, setup `backup` conflict messaging, unsupported directive tolerance, malformed file errors, validation, and rollback.
- [ ] `README.md` is not modified.

## Blocked by

- Issue 1 - Establish SSS-owned Samba layout.
