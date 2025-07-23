# Alerts

The Alerts page displays system alerts and allows configuration of email notifications.

## Email Alert Configuration
- **Fields**: Email address, From address, SMTP server, port, username, password.
- **From Address**: This is the address that will appear in the From field of alert emails. It must be a valid, verified sender for your SMTP service (e.g., the authenticated SMTP user or a domain-verified address). Some SMTP providers will only deliver mail if the From address matches the authenticated user or a verified sender.
- **Save**: Button to save email configuration (shows spinner while saving).
- **Validation**: Inline feedback for all fields.
- **Success/Error Feedback**: Inline messages for save actions.

## Past Alerts
- **Table**: Lists all past alerts with columns for Time, Type, Title, Message, Source, Status.
- **Actions**:
  - **Refresh**: Reload the alerts list.
  - **Mark All as Read**: Mark all alerts as read.
  - **Clear All**: Delete all past alerts (confirmation required).
- **Alert Detail Modal**: View full details of an alert and mark as read.

## UI Details
- Loading spinners and empty state messages.
- Badges for alert type and status.
- Inline feedback for errors and actions.

---

This page helps you monitor system events and configure alert notifications. 