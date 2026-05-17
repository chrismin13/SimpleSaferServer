# Install And Report Discovery Services

## What to build

Update install/update behavior so SimpleSaferServer prepares the SSS Samba layout, treats `smbd` as
the required file-serving daemon, treats `nmbd` as desired legacy discovery, and optionally installs
and starts `wsdd2` for modern Windows Network discovery.

The completed slice should keep core installation strict for `smbd` while allowing discovery
degradation for `nmbd` and `wsdd2`. It should not create a custom `wsdd` service or install both WSD
daemons.

## Acceptance criteria

- [ ] The install/update path invokes the shared Samba layout helper instead of duplicating Samba include edits in Bash where practical.
- [ ] The install/update path prepares the SSS Samba layout but does not create the default `backup` share.
- [ ] `wsdd2` is installed through a separate optional install attempt rather than the fatal core dependency command.
- [ ] If `wsdd2` is unavailable or optional installation fails, the installer warns and continues.
- [ ] The installer does not install or manage `wsdd`.
- [ ] The installer does not create a custom SimpleSaferServer systemd wrapper for `wsdd`.
- [ ] The install/update path enables and starts `smbd`.
- [ ] The install/update path fails when `smbd` cannot become active.
- [ ] The install/update path enables and starts `nmbd` best-effort.
- [ ] The install/update path warns but continues when `nmbd` is inactive or skipped.
- [ ] The install/update path enables and starts `wsdd2` best-effort when `wsdd2` is installed.
- [ ] The install/update path warns but continues when `wsdd2` is unavailable or inactive.
- [ ] Installer output includes a concise summary for `smbd`, `nmbd`, and `wsdd2`.
- [ ] Existing non-discovery install behavior remains unchanged.
- [ ] Focused tests or shell/static tests cover optional `wsdd2`, required `smbd`, best-effort `nmbd`, service summary output, and the helper call path.
- [ ] `README.md` is not modified.

## Blocked by

- Issue 1 - Establish SSS-owned Samba layout.
