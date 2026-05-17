# Discovery service badges use three-tier colors

## What to build

Update the Network File Sharing template so discovery service badges (`nmbd`, `wsdd2`) use
three badge tiers instead of binary green/red:

- `active` → green (`badge-success`)
- `inactive` → yellow (`badge-warning`)
- `unavailable` → grey (`badge-neutral`)

The `smbd` badge stays binary: `active` → green, anything else → red (`badge-danger`), because
`smbd` is the hard file-serving requirement.

This prevents a red "unavailable" badge for `wsdd2` on systems where the package simply is not
installed, and a red "inactive" badge for `nmbd` on systems where Samba's ExecCondition skips it.

## Acceptance criteria

- [ ] `wsdd2` status `unavailable` renders with `badge-neutral` class.
- [ ] `wsdd2` status `inactive` renders with `badge-warning` class.
- [ ] `wsdd2` status `active` renders with `badge-success` class.
- [ ] `nmbd` status `inactive` renders with `badge-warning` class.
- [ ] `nmbd` status `active` renders with `badge-success` class.
- [ ] `smbd` status `inactive` still renders with `badge-danger` class.
- [ ] `smbd` status `active` still renders with `badge-success` class.
- [ ] All existing app factory/route tests remain green.

## Blocked by

None - can start immediately.
