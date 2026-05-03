# 0023 Setup Format Drive GPT

## Summary

- Make setup step 2 match its whole-disk erase contract: selecting a disk and formatting it rebuilds the selected disk as one NTFS backup partition.

## Rules / Constraints

- Preserve Python 3.7 compatibility for Debian 10.
- Keep user-facing messages simple; avoid implementation terms in the setup UI.
- Do not edit `README.md`.
- Check related docs, `index.html`, and `uninstall.sh`.

## Target State

- The setup wizard no longer reuses an old partition layout just because the first partition already exists.
- Formatting a selected whole disk creates a fresh GPT layout with one data partition, then formats that partition as NTFS.

## Phase Checklist

- [x] Phase 1: Rebuild the disk layout before formatting.
- [x] Phase 2: Update docs, UI copy, and focused tests.

## Work Log

### Phase 1

- Changed the setup command adapter to use scriptable `sfdisk` GPT creation instead of interactive `fdisk` input.
- Updated `format_drive` to always recreate the selected disk layout before running `mkfs.ntfs`.

Docs and uninstall impact:

- Updated `docs/setup.md` and checked the existing `index.html` Setup Guide link.
- Added `fdisk` to the installer and manual install dependency list so `sfdisk` is present on minimal Debian/Ubuntu systems.
- `uninstall.sh` does not need changes because no files, services, timers, or state directories were added.

Verification:

- `.venv/bin/python -m pytest tests/test_setup_wizard.py tests/test_setup_command_adapter.py` passed.
- `.venv/bin/python -m ruff check simple_safer_server/routes/setup_wizard.py simple_safer_server/adapters/setup_commands.py tests/test_setup_wizard.py tests/test_setup_command_adapter.py` passed.
- `git diff --check` passed.

## Decisions

- Use `sfdisk` because it is script-oriented, supports GPT, and is available through the fdisk/util-linux baseline on the supported Debian and Ubuntu targets.
- Use the Microsoft basic data partition type so the single partition is appropriate for an NTFS backup drive.

## Follow-Up Backlog

- None.
