# Network File Sharing

The Network File Sharing page manages SMB shares and service status.

## System Status
- **System Status Card**: Shows overall status, service details (SMB and NetBIOS daemons), and technical details (collapsible).
- **Restart Services**: Button to restart SMB services.
- **Status Badges**: Show current state (operational, warning, error).

## Shares Management
- **Shares Table**: Lists all SMB shares with columns for Name, Path, Writable, Comment, Users, and Actions.
- **Add Share**: Button opens a modal to add a new share.
- **Edit Share**: Button opens a modal to edit an existing share.
- **Delete Share**: Button opens a modal to confirm deletion.
- **Browse**: Folder picker for selecting share paths.
- **Writable**: Checkbox to allow users to write to the share.
- **Users with Access**: Select users who can access the share (leave empty for all users).

## Modals
- **Add/Edit Share**: Forms for creating or editing shares, with validation and feedback.
- **Delete Confirmation**: Modal to confirm share deletion.
- **Folder Picker**: Modal to select a directory for sharing.

## UI Details
- Inline validation and feedback for all fields.
- Spinners and alerts for loading and errors.
- Tooltips for technical explanations.

---

This page allows you to manage network file sharing and user access to shared folders. 