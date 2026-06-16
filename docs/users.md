# Users

The Users page allows administrators to manage user accounts.

## User Table
- **Columns**: Username, Role (Admin/User), Created, Last Login, Actions.
- **Dates**: New users store dates with a UTC timezone. Older user records may have no timezone or no created date. The page still loads those users and shows `Unknown` or `Never` instead of a broken date.
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

---

This page provides full user management for the system.
