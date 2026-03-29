# Internal UI Patterns

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
