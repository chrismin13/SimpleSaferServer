# Cloud Backup

Cloud Backup connects your server to any storage backend supported by the installed rclone.
Setup and the Cloud Backup page share the same connection editor. Most installations need one
connection and one dedicated destination folder; additional connections are available under
**More → Manage connections**.

## Connect storage

1. Choose **Choose destination**, search for your service, and select it.
2. Answer the questions supplied by rclone. Defaults, required values, examples, and advanced
   options come from rclone itself. Guidance is shown beneath each field.
3. Browse to a destination folder, create a folder, or enter the exact path.
4. Review the destination and confirm that it is dedicated to this server's backups, then save.

The questions depend on the provider and your answers, so there is no fixed question count.
**Back** restores the preceding question and its draft configuration. **Cancel** discards the
unsaved connection edits. If only OAuth tokens changed, Cancel preserves them when the saved
configuration still matches the draft's starting configuration. This keeps token refreshes from
folder browsing available to backups. A running backup can delay cancellation until those tokens
can be saved; retry after it finishes. Creating a folder is immediate and is not undone by
cancelling configuration.

Existing connections are read from the managed `rclone.conf`, including MEGA connections. Choose
one to select its folder, or edit it without changing the selected backup path. Saving an extra
connection does not switch the backup destination. Rename and duplicate are available from the
connection's menu and right-click menu. Removing a connection does not delete remote files. The
selected connection cannot be removed until its destination is replaced or cleared in Advanced.
Renaming a selected connection updates its backup path. References from other remotes must be
updated in Advanced before renaming or removing a connection they use.

The summary shows only saved settings. **Change destination** opens the destination folder picker;
**Switch storage connection** selects another remote. **Connection settings** edits that remote's
account, authentication, and provider options. The source path is read-only on this page.
Configuration opens in a dialog with a scrolling body and fixed footer, keeping the status and
schedule in place. Closing it discards the unsaved draft.

## Authorize an account

For rclone's shared OAuth flow, choose **Sign in with browser** and then **Open sign-in page**.
Sign in with the storage service in the new tab. When your browser runs on the server, rclone's
localhost callback can complete automatically. When your browser is on another computer, the
final localhost page may not open: copy its full address and paste it into **Final localhost
address** in SSS. SSS validates the pending OAuth state and forwards the callback to that draft's
private rclone listener. It does not change the provider's registered redirect URI.

Alternatively, choose **Use rclone on another computer**, run the command rclone supplies on a
computer with rclone and a browser, and paste its result. Other authentication methods, including
provider-specific codes or credentials, appear as rclone questions.

Browser sign-in requires rclone's `config/oauthstatus` API; update rclone if the UI offers only
command authorization. A second simultaneous browser authorization may need to wait for the
first, because rclone providers can share a fixed callback port. Go back to change authorization
methods, or cancel to stop the listener. Provider access restrictions and OAuth app approval
requirements still apply. The integration tests exercise the protocol and loopback handoff;
they do not authenticate personal cloud accounts.

## Destination, status, and schedule

The main page shows the saved source and destination, enable/disable controls, a connection test,
backup status, and schedule. **More → Test destination access** lists the selected folder; it does not prove write
permission or run a sync. **Run Backup Now** runs the actual backup task. The task log reports
transfer errors. The schedule uses server time in `HH:MM` format; optional bandwidth limits look
like `512k`, `4M`, or `1G`.

Disabling Cloud Backup keeps connections and the selected path. Setup can skip Cloud Backup and
finish with local storage only. Saving during setup does not activate timers; completing setup
activates the appropriate jobs. `backup.cloud_enabled` must explicitly be `true` or `false`.

Cloud Backup uses `rclone sync`: files in the destination will be overwritten or deleted as needed
to match the local source. Choose a dedicated backup folder. Folder selection shows this warning before
saving; it can also accept an exact path when the provider does not permit directory listing.
Browsing and creating folders use the exact destination path, including the leading slash when
the backend distinguishes absolute paths from paths relative to its default directory.

## Advanced configuration and existing installations

**More → Advanced rclone config** lets administrators inspect, edit, or paste the complete managed file
and an exact destination (`remote:folder` or an absolute local path). It contains stored
credentials. The guided editor and backups use that same file:

- Production: the root user's `~/.config/rclone/rclone.conf`.
- Fake mode: `$SSS_DATA_DIR/rclone/rclone.conf`.

Other remote sections and unknown settings are retained. Rclone and INI serialization may
normalize formatting and comments. Configs encrypted with rclone's config password must be
decrypted using rclone before editing here. Environment-only remotes and inherited `RCLONE_*`
overrides are not imported into the editor; put managed settings in the file.
Opening Advanced reloads the configuration, destination, and enable setting together. Changes
saved elsewhere after that snapshot require reopening the editor before saving.

Drafts live privately on the server and expire after 30 minutes without a request. Refreshing the
page resumes a draft in the same browser session. Restarting SSS ends drafts; saved settings
remain. Saves reject stale configuration instead of overwriting another administrator's changes
or a token refresh. A running SSS backup locks configuration until it finishes. External CLI
edits should also wait until backup and web editing finish.

## Storage Safety Checks

Before a scheduled or manual cloud backup starts, SimpleSaferServer checks the configured storage location.

The check confirms:

- the source passed to the backup command matches the configured storage folder
- the configured storage path exists
- the `.simple-safer-server/storage.json` marker file exists
- the marker file contains the storage ID saved in the app config
- the marker file can be read
- the storage folder can be written to
- the test file written by the app can be read back
- the test file can be deleted

For a drive managed by SimpleSaferServer, the check also confirms that the app-managed mount point is mounted and that the mounted filesystem UUID matches the configured drive UUID. For an existing folder, the app does not mount it, but it records where that folder was mounted when it was selected. If the folder later appears under a different mount source, the backup fails until an administrator checks it.

Folder names are read with the same INI parser as the app, so characters such as `%`, `=` and double quotes stay part of the path. If the backup source and saved storage folder disagree, the backup stops before rclone runs. Choose the storage target again on the Storage page to save matching settings.

These checks are deliberately cautious. The safest failure is to skip a backup and alert the administrator. The unsafe failure would be syncing an empty or wrong folder to the cloud and deleting good remote files.

The web UI does not run this full read-write check during normal Dashboard or Storage page loads. That keeps page views from waking sleeping backup drives. Cloud Backup still runs the full check because it is about to read the storage folder anyway.

If the marker file is deleted, SimpleSaferServer treats that as unsafe and blocks Cloud Backup. Use the Storage page to repair the marker after confirming the folder is the correct storage location.

## Fake Mode

Fake mode avoids local system changes, but cloud-backup provider calls can still run when real
credentials and destinations are configured. Use a test destination when developing against a real
provider from fake mode.
