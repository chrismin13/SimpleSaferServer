# Python Accessor Style

## Context

The codebase already mostly avoids Java-style trivial getters and setters. Most `get_*` and
`set_*` methods are service operations that read config, handle secrets, query systemd, mutate
fake-mode state, or coordinate Samba/user state.

## Decision

- Direct attributes are preferred for passive in-memory data.
- `@property` is reserved for cheap, side-effect-free derived facts.
- Explicit methods are preferred when access performs IO, validation, persistence, secrets
  handling, subprocess work, or coordinated state changes.
- Collection-returning service methods should use `list_*` when adding or renaming APIs.

## Cleanup

This pass documents the rule, removes unused SMB compatibility wrappers, and moves user listing
and admin-role persistence behind public `UserManager` methods so routes do not reach into private
storage details.

## Checks

- `index.html` already links to `docs/development.md`.
- `uninstall.sh` does not need changes because this adds no installed files, generated state,
  services, timers, config, or directories.
