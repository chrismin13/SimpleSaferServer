# Alerts

The Alerts page displays system alerts and allows configuration of email notifications.

## Email Alert Configuration
- **Fields**: Email address, From address, SMTP server, TCP port (1-65535), username, password.
- **From Address**: This is the address that will appear in the From field of alert emails. It must be a valid, verified sender for your SMTP service (e.g., the authenticated SMTP user or a domain-verified address). Some SMTP providers will only deliver mail if the From address matches the authenticated user or a verified sender.
- **Password Visibility**: The stored SMTP password loads into the admin editor and is masked by the browser until the administrator reveals it.
- **Save**: Button to save email configuration by disabling during the request.
- **Validation**: Inline feedback for all fields.
- **Success/Error Feedback**: Inline messages for save actions.

## SMTP Credential Help

SMTP settings come from the email provider that will send the alert emails. Most providers want the full email address as the username and an app password instead of the normal account password.

Helpful provider docs:

- [Gmail app passwords](https://support.google.com/mail/answer/185833?hl=en)
- [Gmail SMTP settings](https://support.google.com/mail/answer/7104828?hl=en)
- [Outlook.com SMTP settings](https://support.microsoft.com/en-us/office/pop-imap-and-smtp-settings-for-outlook-com-d088b986-291d-42b8-9564-9c414e2aa040)
- [Microsoft account app passwords](https://support.microsoft.com/en-us/accounts-billing/manage/how-to-get-and-use-app-passwords)
- [Yahoo Mail app password help](https://help.yahoo.com/kb/SLN27791.html)
- [Yahoo Mail SMTP settings](https://help.yahoo.com/kb/imap-server-settings-yahoo-mail-sln4075.html)
- [iCloud Mail server settings](https://support.apple.com/en-us/102525)
- [Apple app-specific passwords](https://support.apple.com/en-us/102654)

For a work, school, or custom-domain email account, use the provider's own mail settings page or ask the mail administrator for the SMTP host, port, username, and app password rules.

## Past Alerts
- **Table**: Lists all past alerts with columns for Time, Type, Title, Message, Source, Status.
- **Actions**:
  - **Refresh**: Reload the alerts list.
  - **Mark All as Read**: Mark all alerts as read.
  - **Clear All**: Delete all past alerts (confirmation required).
- **Alert Detail Modal**: Open an alert from any cell in its table row to view full details and mark it as read.

## UI Details
- Loading spinners and empty state messages.
- Badges for alert type and status.
- Inline feedback for errors and actions.

---

This page helps you monitor system events and configure alert notifications. 
