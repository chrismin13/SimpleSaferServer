# Internal UI Patterns

## Route Authorization

The management interface is admin-only. Non-admin users may exist for Samba and
system file sharing, but they are not Web UI users.

Rules:

- Use `@admin_required` for HTML routes and page-style routes that redirect or render templates.
- Use `@api_admin_required` for JSON API routes used by `fetch()`.
- Do not add login-only management routes. A signed session cookie is not enough by itself because an account can be demoted after the cookie was issued.
- Setup API routes are the exception: they allow anonymous access only until setup is complete, then require admin access for maintenance use.

## Current Visual Style

The current interface still uses custom CSS, but new work should move toward ready-made Web Awesome components and shared templates. Keep existing pages visually consistent while migrating them, and avoid adding new custom component styles when a shared component already covers the job.

`htmx` is vendored at `static/vendor/htmx/2.0.10/htmx.min.js` and loaded by
`templates/base.html`. Use it for server-rendered partial updates when it replaces page-local
`fetch()` glue without adding complicated client-side state. Do not load htmx from a CDN at
runtime.

Web Awesome is being introduced one component at a time. The first locally vendored component is
`wa-callout` from Web Awesome `3.9.0`, served from
`static/vendor/webawesome/3.9.0/components/callout/callout.js`. Use it through shared templates
instead of loading Web Awesome from `ka-f.webawesome.com` at runtime.

Font Awesome `6.4.0` is vendored under `static/vendor/fontawesome/6.4.0/` because the current
templates still use `fas` icon classes. Runtime templates should load that local stylesheet instead
of `cdnjs`. The app uses system font stacks from `static/css/theme.css`; do not add Google Fonts or
another external font host to runtime pages.

## Module Help

Use `templates/partials/module_help.html` when a module page needs shared help text. It renders the
shared Web Awesome callout component and field-level hints from the module contract.
The page route should pass the module contract into the template, and the template should render
`ModuleHelp` text through shared macros instead of copying the same text into the page.
The macros pass visible module help strings through the template `_()` helper so this text is ready
for future gettext catalogs without adding a translation compile step today.

Rules:

- Keep safety warnings visible in the band or main workflow when they affect real services, disks,
  credentials, or host state.
- Use `module_help.field_hint(module, 'field_key')` for form hints that belong to a module field.
  Add the matching `HelpEntry` in the module contract instead of hard-coding the sentence in the
  template.
- Do not use tooltips as the only place for important warnings.
- Hide context-specific warnings when the context does not apply. For example, the DDNS page shows
  the fake-mode live-DNS warning only in fake mode.

Current examples:

- `templates/alerts.html`
- `templates/cloud_backup.html`
- `templates/ddns.html`
- `templates/drive_health.html`
- `templates/network_file_sharing.html`
- `templates/storage.html`
- `templates/system_updates.html`

## Module Plan Preview

Use `templates/partials/module_plan_preview.html` when a setup page or htmx interaction needs to
show what applying a module would do. `GET /fragments/modules/<slug>/plan` renders this partial from
the same module plan data used by `GET /api/modules/<slug>/plan` and `sss module plan <module>`.
Setup pages should use the `setup_plan_details(module, plan, summary)` macro from the same partial
instead of hand-writing repeated `<details>` blocks.

Rules:

- Keep the preview read-only. Apply and uninstall actions must remain explicit lifecycle calls.
- Show changes, missing tools, owned resources, ownership recording timing, warnings, and privileged actions before a module is applied.
- Do not rebuild plan tables in page-specific JavaScript unless the UI genuinely needs client-side state.

## JavaScript Page Copy And Formatting

When a page script needs user-facing text, pass that text from the Flask route into the template as
JSON. The page should render one `<script type="application/json">` block for that copy, and the
script should read it on load. This keeps English as the source text today while leaving a clear path
for gettext/Babel later.

Rules:

- Keep the copy object close to the route or module that owns the page behavior.
- Use complete strings instead of building sentences from small fragments.
- Keep JavaScript fallback strings only as a soft failure path for tests or unusual browser states.
- Use `window.AppFormat` from `static/js/common.js` for dates, relative times, numbers, and
  percentages instead of hand-formatting those values in page scripts.
- Use native `input type="time"` controls for schedule times. Page scripts may call the browser's
  `showPicker()` when available, but do not add a custom time-picker widget unless native controls
  cannot support a required workflow.
- Do not add a JavaScript translation build step until the app ships another language.

Current example:

- `templates/alerts.html`
- `templates/cloud_backup.html`
- `templates/dashboard.html`
- `templates/ddns.html`
- `templates/network_file_sharing.html`
- `templates/setup.html`
- `templates/storage.html`
- `templates/storage_change_drive.html`
- `templates/storage_existing_folder.html`
- `templates/system_updates.html`
- `templates/task_detail.html`
- `templates/users.html`
- `simple_safer_server/modules/alerts/routes.py`
- `simple_safer_server/modules/cloud_backup/routes.py`
- `simple_safer_server/modules/ddns/routes.py`
- `simple_safer_server/modules/file_sharing/routes.py`
- `simple_safer_server/modules/storage/routes.py`
- `simple_safer_server/routes/setup_wizard.py`
- `simple_safer_server/routes/tasks.py`
- `simple_safer_server/routes/users.py`
- `static/js/cloud_backup.js`
- `static/js/ddns.js`
- `static/js/mega_folder_picker.js`
- `static/js/scripts.js`
- `static/js/storage.js`
- `static/js/storage_change_drive.js`
- `static/js/storage_existing_folder.js`
- `static/js/system_updates.js`

## Backup Readiness Checklist

Use `templates/partials/backup_readiness.html` for the 3-2-1 backup checklist. Do not duplicate this
markup in setup or dashboard pages.

Rules:

- Dashboard API clients can load checklist data from `GET /api/backup-readiness`.
- First-run setup UI should load checklist data from `GET /api/setup/readiness`.
- Dashboard htmx refreshes use `GET /fragments/backup-readiness`, which renders the same shared
  partial as HTML.
- Use `window.refreshBackupReadiness()` after setup actions that change storage, cloud backup,
  alerts, or schedule state.
- Treat `skipped` as incomplete protection. It means the user made a choice, not that the server is
  fully protected.

## Layout Stability

Interactive controls should stay anchored when nearby status, validation, or warning UI appears.

Rules:

- Do not place volatile banners above primary action buttons if those banners can appear after a click.
- Prefer global toasts for transient feedback when inline placement is not required.
- When inline feedback is required, do NOT artificially reserve empty whitespace ahead of time. Use a naturally collapsing `.feedback-slot` so the interface remains densely packed and only shifts slightly when an error absolutely must be displayed.
- In modals, prefer a compact footer status line for modal-level errors instead of inserting a full alert above the fields.
- Keep button rows and action bars in a stable position across empty, loading, success, and error states.
- Treat layout shift as a bug. The UI should not move around as the user clicks through normal flows unless movement is necessary for the task itself.
- Keep short, related values in compact horizontal groups when they belong to the same status.
  Add vertical space only when it improves comprehension or the available width requires wrapping.

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
