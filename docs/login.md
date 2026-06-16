# Login Page

The Login page allows administrators to sign in to the SimpleSaferServer management interface.

The broader access model is documented in [Access and Permissions](access.md).

## Fields
- **Username**: Enter your admin username.
- **Password**: Enter your password.
- **Remember me on this browser**: Keeps the admin session after the browser is closed.

## Features
- **Validation**: Both fields are required.
- **Feedback**: Error and success messages are displayed above the form (e.g., invalid credentials, lack of admin privileges).
- **Button**: `Sign in` (submits the form).

## Behavior
- Only administrators can log in to the management interface.
- Non-admin users are shown an error message and cannot access the interface.
- After successful login, users are redirected to the Dashboard.
- If **Remember me on this browser** is not checked, the login uses a normal browser session cookie.
- If **Remember me on this browser** is checked, the signed session cookie lasts for 14 days. The app does not store the password in the browser, and protected pages still check that the signed-in user is still an administrator.

---

If setup is not complete, users are redirected to the Setup Wizard. 
