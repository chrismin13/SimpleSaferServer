# Users

The Users page allows administrators to manage user accounts.

## User Table
- **Columns**: Username, Role (Admin/User), Created, Last Login, Actions.
- **Actions**: Edit or delete users (cannot delete your own account).

## Add User
- **Modal**: Add User form with fields for username, password, and admin checkbox.
- **Validation**: Username (3-32 chars, unique), password (min 4 chars).
- **Feedback**: Inline error messages for invalid input or duplicate usernames.

## Edit User
- **Modal**: Edit User form with fields for new password and admin checkbox.
- **Validation**: Password (min 4 chars, optional).
- **Feedback**: Inline error messages for invalid input.
- **Admin Restriction**: When editing your own account, the admin checkbox is disabled and shown as unavailable. The server also rejects requests that would remove your own admin privileges while you are logged in.

## Alerts
- **Success/Error Alerts**: Shown for all user actions (add, edit, delete).

## Behavior
- User list updates live after changes.
- All actions are performed via modals for a smooth experience.
- Creating a user or changing a password also updates the Samba account used for SMB access. If Samba cannot accept the password, the web-login password is not saved, so the web UI and SMB access stay on the same credentials.

## What Happens Behind The Scenes

SimpleSaferServer keeps a small app-owned user record for the Web UI. It also creates or updates a matching Samba user so the same person can access SMB file shares.

- Admin users can sign in to the Web UI.
- Non-admin users are useful for SMB file sharing access, but they cannot manage the server in the Web UI.
- Password changes are applied to the app user and the Samba user together.
- If the Samba password update fails, the app does not save the Web UI password change. This avoids a confusing split where one password works in the browser and another password works for file sharing.
- Deleting a SimpleSaferServer user also removes the matching Samba account managed by the app.

---

This page provides full user management for the system.
