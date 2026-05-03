# 0017 Dev Bootstrap Path Fix

## Summary

- Fixed `install_dev.sh` so it works when launched from outside the repository root.
- Made the script choose the modern or legacy runtime requirements file from the virtualenv's Python version.

## Rules / Constraints

- Preserve Python 3.7 compatibility for Debian 10.
- Keep local development setup rooted in the repository checkout.
- Check related docs, `index.html`, and `uninstall.sh`.

## Target State

- `bash /path/to/SimpleSaferServer/install_dev.sh` creates `/path/to/SimpleSaferServer/.venv`
  and installs requirements using absolute paths to files in that checkout.
- Python 3.9 and newer use `requirements.txt`.
- Python runtimes older than 3.9 use `requirements-legacy-py37.txt` and keep pip below 24.1.

## Phase Checklist

- [x] Phase 1: Repair dev bootstrap path handling and dependency selection.
- [x] Phase 2: Add regression coverage and check related documentation/index/uninstall impact.

## Work Log

### Phase 1

- Anchored `install_dev.sh` paths to the script directory.
- Added a missing-file preflight for the selected runtime requirements file and `requirements-dev.txt`.
- Kept the pip 24.1 cap only for Python runtimes older than 3.9 because that cap is needed for the legacy dependency lane.

Docs and uninstall impact:

- `docs/development.md` already documents `bash install_dev.sh` and the modern/legacy requirements lanes.
- `docs/manual_install.md` already documents the runtime requirements split for manual installs.
- `index.html` already links to the development and manual install docs.
- `uninstall.sh` does not need changes because the dev script only manages the repository-local `.venv`.

Verification:

- Added `tests/test_install_dev.py` to exercise the script from outside the checkout with fake Python/pip commands.

## Decisions

- The dev bootstrap should use the virtualenv's actual Python version rather than assuming that every dev environment can install the security-supported Python 3.13 dependency set.

## Follow-Up Backlog

- None.
