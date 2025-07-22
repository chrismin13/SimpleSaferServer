# Login Page

The Login page allows administrators to sign in to the SimpleSaferServer management interface.

## Fields
- **Username**: Enter your admin username.
- **Password**: Enter your password.

## Features
- **Validation**: Both fields are required.
- **Feedback**: Error and success messages are displayed above the form (e.g., invalid credentials, lack of admin privileges).
- **Button**: `Sign in` (submits the form).

## Behavior
- Only administrators can log in to the management interface.
- Non-admin users are shown an error message and cannot access the interface.
- After successful login, users are redirected to the Dashboard.

---

If setup is not complete, users are redirected to the Setup Wizard. 