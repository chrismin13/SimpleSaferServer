# Establish SSS-Owned Samba Layout

## What to build

Create the shared Samba layout foundation that moves SimpleSaferServer ownership out of ordinary
share marker comments and into SSS-owned include files.

The completed slice should provide an idempotent helper that can be called by explicit
install/update/setup/share-management paths. It should ensure the SSS globals file, SSS shares file,
and marker-wrapped include lines exist in the correct places, validate the effective Samba config,
and roll back when publishing a layout change would leave Samba broken.

## Acceptance criteria

- [ ] The helper creates the SSS globals file from a repository template.
- [ ] The globals template includes only the agreed global policy: `map to guest = never` and `disable netbios = no`.
- [ ] The globals file header explains that SimpleSaferServer may refresh the file and that site-specific overrides belong after the SSS global include if an admin intentionally wants to override SSS defaults.
- [ ] The helper creates the SSS shares file with a header when the file is missing.
- [ ] The shares file header says normal share changes should use the Web UI and unsupported manual directives may be overwritten by Web UI edits.
- [ ] SSS-owned Samba config files are written root-owned with mode `0644` in real runtime paths.
- [ ] The helper inserts the global include inside `[global]`, as late as possible before the first non-global section.
- [ ] The helper inserts the shares include at the end of the main Samba config.
- [ ] Running the helper repeatedly does not duplicate include blocks.
- [ ] The helper leaves unrelated `smb.conf` content unchanged.
- [ ] The helper fails closed when SSS include marker blocks are malformed.
- [ ] The helper validates the effective Samba config with `testparm` before publishing changes.
- [ ] The helper rolls back layout changes when validation fails.
- [ ] The helper does not run from ordinary app startup or status polling.
- [ ] Focused tests cover include placement, idempotency, malformed markers, file creation, permissions where practical, validation, and rollback.
- [ ] No managed-share behavior is migrated in this slice beyond creating the empty SSS shares file.
- [ ] `README.md` is not modified.

## Blocked by

None - can start immediately.
