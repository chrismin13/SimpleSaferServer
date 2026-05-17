# Document Samba Ownership And Discovery

## What to build

Update operator-facing documentation and the public documentation index copy so it matches the new
Samba ownership and discovery behavior.

The completed slice should explain SSS-owned include files, the role of `smbd`, `nmbd`, and
`wsdd2`, setup conflict behavior, manual-edit expectations, and uninstall cleanup. Do not edit the
README.

## Acceptance criteria

- [ ] Network File Sharing docs describe SSS-owned Samba files and file-path ownership.
- [ ] Network File Sharing docs explain that comments in SSS-owned files are for humans and are not the ownership boundary.
- [ ] Network File Sharing docs explain that normal share changes should use the Web UI.
- [ ] Network File Sharing docs explain that unsupported manual directives may be overwritten by Web UI edits.
- [ ] Network File Sharing docs explain that existing shares outside the SSS shares file are unmanaged and will not be overwritten.
- [ ] Network File Sharing docs explain the `backup` share conflict and retry behavior.
- [ ] Network File Sharing docs explain `smbd`, `nmbd`, and `wsdd2` by purpose.
- [ ] Install docs mention that `wsdd2` is optional modern Windows discovery support.
- [ ] Manual install docs mention the SSS Samba layout/helper behavior and the optional `wsdd2` package.
- [ ] Uninstall docs mention removal of SSS Samba include blocks and owned Samba files.
- [ ] Uninstall docs state that shared packages such as Samba and `wsdd2` are left installed.
- [ ] Public `index.html` uninstall copy matches the new owned-file cleanup behavior.
- [ ] Existing documentation links in `index.html` remain valid.
- [ ] `README.md` is not modified.

## Blocked by

- Issue 1 - Establish SSS-owned Samba layout.
- Issue 2 - Move managed shares to the SSS shares file.
- Issue 3 - Install and report discovery services.
- Issue 4 - Track three file-sharing services in the Web UI.
- Issue 5 - Clean up SSS-owned Samba config on uninstall.
