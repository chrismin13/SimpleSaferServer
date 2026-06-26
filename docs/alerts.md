# Alerts

The Alerts page displays system alerts and allows configuration of email notifications.

The page shows its purpose, setup note, and warning from the Alerts module contract in
`simple_safer_server/modules/alerts/module.py`. Keep alert setup help there so the Web UI, setup
flow, CLI, and docs can reuse the same wording.

## Email Alert Configuration
- **Fields**: Email address, From address, SMTP server, TCP port (1-65535), username, password.
- **From Address**: This is the address that will appear in the From field of alert emails. It must be a valid, verified sender for your SMTP service (e.g., the authenticated SMTP user or a domain-verified address). Some SMTP providers will only deliver mail if the From address matches the authenticated user or a verified sender.
- **Password Visibility**: The stored SMTP password loads into the admin editor and is masked by the browser until the administrator reveals it.
- **Save**: Button to save email configuration by disabling during the request.
- **Validation**: Inline feedback for all fields.
- **Success/Error Feedback**: Inline messages for save actions.

Alerts send email with Python's SMTP support using the saved SMTP settings. SimpleSaferServer does
not require `msmtp` for alert delivery.

## Required Host Tools

Alerts use SMTP TLS verification through Python's default SSL context. The Alerts module declares
`update-ca-certificates` as a required host tool so the setup plan can catch hosts without the
system CA bundle support that TLS mail providers usually need. The base installer does not install
`ca-certificates` automatically.

The SMTP settings are written through the SimpleSaferServer privileged action registry. The matching
helper action is `alerts.write-smtp-config`, and its payload is passed as JSON on stdin so the SMTP
password does not appear in process arguments.
After a successful write, the helper records the SMTP config path in `<data>/ownership.json`.

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
