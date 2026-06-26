# API Responses

SimpleSaferServer API routes use a Data + Problem response contract. The browser receives normal
data in a small success envelope, and failures use RFC 9457 Problem Details with real HTTP status
codes.

## Success Responses

Success responses return a JSON object with `data`. A route may also include `message` when the UI
needs operator-facing confirmation text.

```json
{
  "data": {
    "folders": ["Backups"],
    "path": "/",
    "parent": "/"
  }
}
```

```json
{
  "data": {},
  "message": "Backup started."
}
```

Do not return `success: true` from API endpoints. The HTTP status code and the presence of a
normal data envelope already communicate success.

## Problem Responses

Failures return Problem Details:

```json
{
  "type": "https://github.com/chrismin13/SimpleSaferServer/blob/main/docs/api_responses.md#validation-error",
  "title": "Validation error",
  "status": 400,
  "detail": "Folder name is required."
}
```

Use real HTTP status codes. Do not return `200` with `success: false`.

Problem `type` values are stable documentation anchors. Use the closest existing anchor for common
cases, and add a specific anchor when the UI or tests need a durable machine-readable distinction.

## Service Contracts

Routes are the JSON boundary. Service methods should return normal Python values and raise
app-level exceptions that routes can map to Problem Details.

Use dataclasses for repeated result shapes:

```python
@dataclass(frozen=True)
class MegaFolderList:
    folders: List[str]
    path: str
    parent: str
```

Use explicit `as_dict()` methods when the API field names differ from Python field names or when
the object contains secrets, internal state, or values that should not be serialized blindly.

Avoid returning raw dictionaries from services when the shape is repeated or important. Avoid
returning `(payload, status_code)` from services; raise a problem exception for failures instead.

## Frontend Contract

Browser code should use the shared API helper in `static/js/common.js`. The helper parses success
envelopes and throws a structured error for Problem Details, so page scripts do not need to check
`success`, `error`, and `message` manually.

## Shared Setup Checklist

`GET /api/backup-readiness` returns the shared 3-2-1 backup-readiness checklist. Setup and dashboard
UI should use this contract instead of each page inventing its own completion rules.
The response includes display-ready text such as `count_label` and each item's `status_label`, so
browser refreshes do not rebuild checklist labels in JavaScript.
`GET /api/setup/readiness` returns the same shape during first-run setup, where setup API routes are
allowed before the first admin session is fully established.
`GET /fragments/backup-readiness` renders the dashboard version as an HTML fragment for htmx, using
the same checklist builder and shared Jinja partial.

```json
{
  "data": {
    "status": "incomplete",
    "complete": false,
    "title": "Backup protection needs setup",
    "detail": "Finish the checklist so the server has a safer backup setup.",
    "completed_required_count": 3,
    "required_count": 5,
    "count_label": "3 of 5 complete",
    "items": [
      {
        "key": "cloud_backup",
        "title": "Set up cloud backup",
        "detail": "Cloud backup was skipped, so this server does not yet have an off-site SSS copy.",
        "status": "skipped",
        "status_label": "Skipped",
        "complete": false,
        "action_label": "Set Up Cloud Backup",
        "action_url": "/cloud_backup",
        "required": true
      }
    ]
  }
}
```

Known item keys are `storage`, `network_access`, `cloud_backup`, `alerts`, and `schedule`.

## Module Checks

`GET /api/modules/<slug>/check` runs read-only setup checks for one module. Today this reports the
external tools declared by the module contract. Missing non-optional tools are `blocking: true`.
The endpoint does not install packages or write host config.

```json
{
  "data": {
    "module": {
      "slug": "cloud-backup",
      "title": "Cloud Backup",
      "applied": false
    },
    "check": {
      "module_slug": "cloud-backup",
      "summary": "Required tools are missing.",
      "blocking": true,
      "required_tools": [
        {
          "name": "rclone",
          "purpose": "Runs the cloud sync after storage safety checks pass.",
          "optional": false,
          "available": false,
          "path": "",
          "blocking": true,
          "status": "missing"
        }
      ]
    }
  }
}
```

`GET /api/modules/<slug>/plan` includes the same `available`, `path`, and `blocking` fields on
`required_tools` so a plan preview can show missing prerequisites before the user applies a module.
`GET /fragments/modules/<slug>/plan` renders that same plan as an admin-only HTML fragment using
`templates/partials/module_plan_preview.html`. Use the fragment from htmx or setup pages when the
browser needs a read-only plan preview instead of rebuilding the same tables in JavaScript.
`GET /api/modules`, `/check`, and `/plan` include `module.applied` when the route can read the
current runtime. The value is based on ownership records in `<data>/ownership.json`.

`POST /api/modules/<slug>/apply` uses the same module lifecycle as `sss module apply <module>`.
It reruns the module's read-only checks before recording ownership. If a non-optional tool is
missing, the response is a `409` problem with slug `module-apply-not-available`, and no ownership
records are written.

Module routes that write host config can require this apply step first. If setup ownership is
missing, the response is a `409` problem with slug `module-setup-required`.

## Common Problem Types

### validation-error

The request was syntactically valid JSON, but fields were missing or invalid.

### request-body-must-be-json-object

The route requires a JSON object body and received no JSON body, invalid JSON, or a JSON value that
is not an object.

### forbidden

The authenticated operator cannot perform the requested action.

### unauthorized

The request needs a valid login session or credentials.

### api-login-required

The API request needs a fresh authenticated session.

### api-admin-required

The authenticated session no longer belongs to an administrator.

### login-failed

The submitted login credentials are invalid.

### login-admin-required

The submitted login account exists but is not an administrator.

### not-found

The requested resource does not exist.

### conflict

The request conflicts with current system state.

### operation-failed

The server could not complete an expected local operation.

### service-unavailable

The requested capability is unavailable in the current runtime or operating system environment.

### module-not-found

The requested module slug is not registered.

### module-apply-not-available

The requested module cannot be applied. Read-only modules use this when they expose status or plans
but do not own setup actions.

### module-setup-required

The module has not been applied yet, so SSS will not write host config for it. Apply the module
through the setup flow or module API before saving settings that touch owned files or manually
running the module's background job.

### module-uninstall-not-available

The requested module cannot be uninstalled through the generic module lifecycle. Read-only modules
use this when they do not own uninstall actions. Writable modules also use it when their ownership
manifest includes resources that need module-specific cleanup, such as host config files, storage
markers, or fstab entries.

Successful module uninstall responses include removed ownership records and any safe app-owned
file paths removed from SSS config/state. Safe app-owned config sections and secret keys may also
be removed. Host-file cleanup remains module-specific, and the manifest is left intact when generic
cleanup is not enough.

### cloud-backup-task-not-found

The Cloud Backup task is missing from the configured task service.

### cloud-backup-missing-mega-credentials

MEGA credentials were required for the operation, but no request credentials or stored credentials
were available.

### cloud-backup-rclone-error

`rclone` returned an error while performing a Cloud Backup provider operation.

### cloud-backup-rclone-config-write-failed

SimpleSaferServer could not write the rclone configuration needed for Cloud Backup.

### alerts-fake-mode-required

The requested alert testing action is only available in fake mode.

### alert-not-found

The requested alert record does not exist.

### system-updates-read-only

The requested operating-system update action is read-only in SimpleSaferServer. Manage apt,
stale locks, and Livepatch directly on the operating system.

### system-updates-settings-read-only

Automatic apt settings are read-only in SimpleSaferServer.

### user-not-found

The requested management user does not exist.

### user-validation-error

The requested user-management change is missing required fields or violates account safety rules.

### task-not-found

The requested scheduled task does not exist.

### task-operation-failed

The requested task action could not be completed.

### storage-validation-error

The requested dashboard storage action is missing required configuration or targets an unavailable
drive.

### storage-apt-lock-blocked

The requested restart or shutdown is blocked because apt or dpkg is running.

### backup-drive-validation-error

The requested backup-drive setup action is missing required data or cannot be applied to the
selected drive.

### backup-drive-operation-failed

SimpleSaferServer could not complete a backup-drive setup operation.

### smb-validation-error

The requested network-file-sharing change is missing required fields or contains invalid values.

### smb-operation-failed

SimpleSaferServer could not complete a Samba share or service operation.
