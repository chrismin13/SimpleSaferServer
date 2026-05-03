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

### system-updates-operation-conflict

The requested apt operation conflicts with the current package-manager state.

### system-updates-lock-removal-failed

SimpleSaferServer could not remove stale apt lock files.

### livepatch-setup-failed

Ubuntu Livepatch setup failed.

### drive-health-telemetry-not-found

Telemetry has not been generated yet, so there is no file to download.

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
