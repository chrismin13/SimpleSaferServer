# Installer OS Preflight

## Summary

- Added an installer preflight that checks whether the host can run the Debian-style install path before any package or clone work starts.

## Rules / Constraints

- Preserve Python 3.7 compatibility for Debian 10.
- Keep the installer useful for Debian/Ubuntu derivatives when they provide APT and systemd.
- Check related docs, `index.html`, and `uninstall.sh`.

## Target State

- `install.sh` fails early on clear non-APT or non-systemd hosts.
- Direct Debian and Ubuntu hosts install normally.
- Debian/Ubuntu derivatives continue with a warning because package availability is ultimately proven by `apt-get`.
- Unsupported OS-family detection can be bypassed with `--unsupported-os-ok`, but missing host tools and package failures still stop the install.

## Phase Checklist

- [x] Phase 1: Add installer preflight and tests.
- [x] Phase 2: Move OS support metadata into a shared Python module.
- [x] Phase 3: Update user/operator docs.

## Work Log

### Phase 1

- Added early installer checks for `apt-get`, `dpkg`, `systemctl`, and `os-release` metadata.
- Added test-only preflight controls so tests can run without installing packages.

Docs and uninstall impact:

- Updated `README.md`, `docs/install.md`, `docs/uninstall.md`, `docs/system_updates.md`, and `index.html`.
- Kept `docs/manual_install.md` focused on the manual path.
- `uninstall.sh` does not need changes because this added no installed files, generated state, services, timers, config, or directories.

Verification:

- Record final commands and results in the implementation handoff.

## Decisions

- Prefer capability-first install gating over maintaining a complete derivative allowlist.
- Use `ID_LIKE` as a warning-and-continue signal for Debian/Ubuntu derivatives.
- Keep a small shell preflight in `install.sh` because curl-piped installs cannot rely on repo Python code before cloning or dependency installation.

## Follow-Up Backlog

- Consider showing derivative OS-family warnings in the System Updates page if admins need the same context after install.
