# Issue 010: Strict Custom Duration Field & Standardized Modal Form Alignment

Type: AFK

## Parent

PRD: Disable Scheduled Task Schedules

## What to build

Enhance the Disable Schedule modal dialog to support an exact **Custom Duration** while normalizing footer button styles to match global layout conventions. Integrate a **Custom** radio option into the duration selection grid. Below the grid, append a naturally collapsible custom duration input group pre-filled with a default of `48` hours. Enforce strict arrowless input fields using `<input type="text" inputmode="numeric" pattern="[0-9]*">` to prevent spinner controls and optimize mobile keypads (matching the SMTP port field). Wrap footer action buttons in standard containers with solid button styles (`btn btn-secondary` and `btn btn-warning`), reporting client-side validation failures inside a dedicated left-aligned inline message element.

## Acceptance criteria

- [ ] Disable Schedule modal grid includes a Custom option forming a balanced layout.
- [ ] Selecting Custom duration reveals the collapsible custom hours input group and focuses the field automatically.
- [ ] Custom duration field enforces an arrowless interface using `type="text"`, `inputmode="numeric"`, and `pattern="[0-9]*"`.
- [ ] Custom duration field is pre-filled with a default value of 48 hours.
- [ ] Modal footer buttons are grouped inside a right-aligned action container.
- [ ] Modal Cancel button uses standard non-shrunk styling (`btn btn-secondary`).
- [ ] Modal Disable Schedule button uses standard non-shrunk styling (`btn btn-warning`).
- [ ] Invalid non-integer or zero custom hour submissions display clear inline validation errors inside the dedicated modal footer message slot without layout shifting.
- [ ] Successful custom duration submissions transmit the correct integer hours payload to the backend API.

## Blocked by

- Issue 009: Task Toolbar Layout Stabilization & Premium Button Color Refresh
