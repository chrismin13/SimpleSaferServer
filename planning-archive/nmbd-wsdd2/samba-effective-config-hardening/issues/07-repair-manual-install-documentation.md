# Repair Manual Install Documentation

## What to build

Update manual install documentation so the Samba layout helper command works from the installed app
directory and mirrors the automated installer's import-path assumptions. The docs should remain
operator-facing and should not require the app to be installed as a Python package.

## Acceptance criteria

- [ ] Manual install docs run the Samba layout helper from the installed app directory.
- [ ] Manual install docs insert the installed app path into Python's import path before importing the app package.
- [ ] The documented command still creates or refreshes the SimpleSaferServer-owned Samba layout without creating the default `backup` share.
- [ ] Related Network File Sharing docs remain consistent with Effective Samba Config and Unmanaged Samba Share terminology if referenced.
- [ ] `index.html` documentation links remain valid.
- [ ] `README.md` is not modified.

## Blocked by

None - can start immediately.
