# Internal UI Patterns

## Layout Stability

Interactive controls should stay anchored when nearby status, validation, or warning UI appears.

Rules:

- Do not place volatile banners above primary action buttons if those banners can appear after a click.
- Prefer global toasts for transient feedback when inline placement is not required.
- When inline feedback is required, reserve space with a feedback slot so forms, modal footers, and action rows do not jump.
- In modals, prefer a compact footer status line for modal-level errors instead of inserting a full alert above the fields.
- Keep button rows and action bars in a stable position across empty, loading, success, and error states.
- Treat layout shift as a bug. The UI should not move around as the user clicks through normal flows unless movement is necessary for the task itself.

Current examples:

- `templates/drive_health.html`
- `templates/cloud_backup.html`
- `templates/users.html`
- `templates/network_file_sharing.html`
- `templates/setup.html`

## Async Action Buttons

Action buttons that trigger network or system work should use a simple disabled state.

Rules:

- Disable the button immediately on click to prevent duplicate submissions.
- Keep the button disabled for a short minimum duration so very fast actions do not flash enabled/disabled states.
- Use the existing toast, inline form message, or status panel for completion and error feedback.
- Use `window.AsyncButtonState` from `static/js/common.js` for button locking rather than creating page-local loading helpers.
- Use page-level loading UI only when the whole region is loading; do not use button spinners as a substitute for list, card, or panel loading states.

Current examples:

- `templates/cloud_backup.html`
- `templates/users.html`
- `templates/network_file_sharing.html`
- `templates/setup.html`
- `templates/dashboard.html`

## Actionable Lists And Tables

When a list or table row has row-level actions in an `Actions` column, expose the same actions on right-click for the row.

Rules:

- Keep the visible action buttons on the right.
- Add the right-click menu as an extra shortcut, not a replacement.
- Reuse the same handlers for both the inline buttons and the context menu items.
- For new implementations, use `window.ActionContextMenu` from `static/js/common.js`.

Current examples:

- `templates/users.html`
- `templates/network_file_sharing.html`
