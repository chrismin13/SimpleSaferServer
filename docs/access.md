# Access and Permissions

SimpleSaferServer separates management access from file-share access.

## Management Web UI

- The SimpleSaferServer web UI is for administrators only.
- The first account created during setup is an administrator.
- Any later account must also have the admin flag enabled before it can sign in to the web UI.
- A valid username and password are not enough for web UI access by themselves. The account must also be marked as an administrator.
- Protected management pages re-check administrator status on every request. If an account is demoted after signing in, its existing web session no longer has management access.

## Management APIs

- Management API endpoints also require an administrator session.
- API authentication failures return JSON responses with HTTP status codes instead of redirecting to a web page.
- `401` means the browser does not have a valid management session.
- `403` means the session exists but the account is not currently an administrator.

## Admin Trust Model

SimpleSaferServer is a root-run local management tool. Administrators are trusted operators with
server-level access, so credential editor screens may show stored credentials and credential-bearing
configuration when that is useful for inspection or edits.

The app should still avoid accidental credential spread. Do not put secrets in broad status
responses, unrelated UI, logs, process arguments, or world-readable files.

## Non-Admin Accounts

- Non-admin accounts can exist for file sharing and related system access.
- Non-admin accounts cannot sign in to the SimpleSaferServer management interface.
- If a user only needs access to the backup share over the network, that user does not need web UI access.

## Why This Matters

- The web UI can change backup settings, schedules, alerts, cloud destinations, and managed storage configuration.
- Some actions also trigger privileged system changes such as service restarts, Samba updates, apt package operations, Livepatch setup, and managed `/etc/fstab` changes.
- Keeping the management interface admin-only avoids mixing day-to-day file access with system administration privileges.

## Related Documentation

- [Setup Wizard](setup.md)
- [Login Page](login.md)
- [Users](users.md)
- [System Updates](system_updates.md)
- [Fake Mode](fake_mode.md)
