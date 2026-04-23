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

---

This page provides full user management for the system.
