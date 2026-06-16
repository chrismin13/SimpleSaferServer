# Feature Visibility

SimpleSaferServer can hide top-level Web UI menus through the main config file.

This is meant for simple cleanup. For example, if a server does not use DDNS or cloud backup, an
admin can hide those pages so the interface is shorter.

This is not a security boundary. SimpleSaferServer is still an admin-only local management tool.
An administrator with server access can edit the config file, restart services, and use system tools
directly.

## Config Setting

Edit:

```text
/etc/SimpleSaferServer/config.conf
```

Set `disabled_features` in the `[system]` section:

```ini
[system]
disabled_features = ddns, cloud_backup
```

The value is a comma-separated list. Spaces are allowed.

After saving the file, reload the page in the browser. The web app reads this setting on each
request, so a service restart is not normally needed.

## Supported Values

Use these values in `disabled_features`:

| Value | What it hides and blocks in the Web UI |
| --- | --- |
| `overview` | Overview page, dashboard storage controls, system resource API, and the `Check Mount` task page |
| `file_sharing` | File Sharing page and Samba Web UI APIs |
| `users` | Users page and user management APIs |
| `drive_health` | Drive Health page, drive health APIs, backup drive setup APIs, and the `Drive Health Check` task page |
| `ddns` | DDNS page, DDNS APIs, and the `DDNS Update` task page |
| `cloud_backup` | Cloud Backup page, cloud backup APIs, and the `Cloud Backup` task page |
| `system_updates` | System Updates page, system update APIs, and the `App Update` task page |
| `alerts` | Alerts page and alert APIs |

Some common alternate names also work, such as `network_file_sharing`, `samba`, `backup`, `updates`,
and `app_update`.

## What This Does Not Do

This setting does not uninstall packages, remove config files, stop systemd timers, or change Linux
permissions.

If you want scheduled work to stop, disable that task's schedule before hiding the feature, or manage
the related systemd timer directly.

If you want to remove SimpleSaferServer data during uninstall, use the normal uninstall process. The
feature visibility setting lives inside the main config file, so it is removed with the app config.

## Related Documentation

- [Access and Permissions](access.md)
- [Dashboard](dashboard.md)
- [Uninstallation Guide](uninstall.md)
