# Network File Sharing

The Network File Sharing page manages Samba shares and Samba service status.
It also includes the server name. This is the name you'll use to find this
server on your network. Scheduled task alert emails include it in the subject.

SimpleSaferServer distinguishes between two kinds of Samba shares:

- **SimpleSaferServer-managed shares**: share sections in `/etc/samba/simple_safer_server_shares.conf`
- **Unmanaged Samba Shares**: non-system shares Samba loads from the Effective Samba Config after
  SimpleSaferServer-owned include blocks are excluded

That ownership split matters because SimpleSaferServer only edits shares that it can identify safely.
Use the Web UI for normal SimpleSaferServer share changes so the app can validate Samba, publish
the owned file safely, and gracefully reload the configuration (falling back to a full restart 
only if the reload fails or the daemon is inactive).
If a publish fails after the owned shares file is replaced, SimpleSaferServer restores the previous
owned shares file and reloads or restarts `smbd` so Samba returns to the last known-good share set.

## What the Page Shows

- **Managed shares table**: lists only SimpleSaferServer-managed shares
- **Add Share**: creates a new SimpleSaferServer-managed share
- **Edit Share**: updates a SimpleSaferServer-managed share
- **Delete Share**: removes a SimpleSaferServer-managed share
- **Unmanaged share warning**: appears when SimpleSaferServer detects other non-system Samba shares
  in Samba's Effective Config, or when that Effective Config cannot be verified on page load
- **Server Name**: changes the OS hostname, SimpleSaferServer's stored server name,
  and the local hostname entry used by the server itself
- **Restart Services**: restarts `smbd`, `nmbd`, and `wsdd2`
  Restarting Samba disconnects anyone who is currently connected to a share, so active file copies or other SMB activity will drop.

The technical service row tracks three file-sharing services:

- `SMB Daemon (smbd)`: serves file shares
- `NetBIOS Discovery (nmbd)`: helps older Windows network browsing find this server
- `Windows Discovery (wsdd2)`: helps modern Windows network browsing find this server

The overall status is `Operational` when `smbd` is active and both discovery services are either
active or unavailable (not installed). It is `Partial` when `smbd` is active but at least one
discovery service is inactive or in an error state. It is `Down` when `smbd`
is not active, because direct file serving is unavailable.

Changing the server name also restarts Samba discovery/services so the new name is
advertised without rebooting. Connected file-sharing clients may need to reconnect.

If Unmanaged Samba Shares are detected, the page shows a small warning button with the count.
That button opens a modal that:

- lists the unmanaged share names
- explains that SimpleSaferServer will not edit or remove them
- links to this document for manual conversion guidance

If the page cannot verify Unmanaged Samba Shares, it shows the same compact warning control with a
verification failure message. The managed-share table can still load because it comes from the
SimpleSaferServer-owned shares file, but the absence of unmanaged names should not be treated as a
clean Samba config until verification succeeds.

## SimpleSaferServer-Managed Share Format

SimpleSaferServer has a dedicated Samba layout helper for install, update, setup,
and share-management paths. That helper owns these include files when those paths
prepare the Samba layout:

- `/etc/samba/simple_safer_server_globals.conf`
- `/etc/samba/simple_safer_server_shares.conf`

The helper wires those files into `/etc/samba/smb.conf` with small
SimpleSaferServer marker-wrapped include blocks. It validates the effective Samba
configuration before publishing the layout and restores the original files if
validation fails.

File paths are the ownership boundary:

- `/etc/samba/smb.conf` remains the system/admin-owned Samba entrypoint.
- `/etc/samba/simple_safer_server_globals.conf` is owned by SimpleSaferServer and may be refreshed
  by install, update, setup, and share-management paths.
- `/etc/samba/simple_safer_server_shares.conf` is owned by SimpleSaferServer and contains only
  SimpleSaferServer-managed shares.

A SimpleSaferServer-managed share is a normal Samba share section in
`/etc/samba/simple_safer_server_shares.conf`:

```ini
[backup]
   path = /media/backup
   writeable = Yes
   create mask = 0777
   directory mask = 0777
   public = no
   comment = Default backup share created by SimpleSaferServer setup
   valid users = admin
```

The file path is the ownership marker. Comments in the file are only human guidance, so changing
or deleting comments does not change whether SimpleSaferServer treats a share as managed.
This lets SimpleSaferServer:

- show only its own shares in the editable table
- update only the shares it owns
- delete only the shares it owns
- remove only its owned include file during uninstall

## Supported SimpleSaferServer Share Settings

SimpleSaferServer-managed shares support only these share fields:

- share name
- `path`
- `writeable` or `writable`
- `comment`
- `valid users`

SimpleSaferServer also writes these fixed defaults into every managed share:

- `create mask = 0777`
- `directory mask = 0777`
- `public = no`

Those defaults are intentional. They keep the managed share format narrow and predictable so the app can rewrite it safely months later.

## Settings SimpleSaferServer Does Not Preserve or Manage

SimpleSaferServer is not a general Samba configuration editor.
If a share depends on other Samba directives, keep managing it manually outside the app.
Unsupported manual directives in the SimpleSaferServer shares file do not block the shares table,
but editing that share in the Web UI rewrites the share in the supported format and may drop those
unsupported directives.

Examples of settings that SimpleSaferServer does not preserve or manage:

- `browseable`
- `guest ok`
- `read only`
- `write list`
- `read list`
- `force user`
- `force group`
- `hosts allow`
- `hosts deny`
- recycle-bin settings
- veto or hide rules
- symlink rules
- ACL or inheritance tuning
- any custom Samba directive not listed in the supported settings above

## Why Unmanaged Shares Are Hidden From Editing

An Unmanaged Samba Share may contain Samba options that the SimpleSaferServer UI does not understand.
If the app tried to import and rewrite those blocks automatically, it could silently remove or change settings that still matter.

SimpleSaferServer therefore takes the safer path:

- ask Samba to parse the Effective Samba Config
- detect non-system shares that are not from the SimpleSaferServer-owned shares file
- warn the user that they exist
- leave them active in Samba
- refuse to edit or remove them

The inspection writes a stripped candidate config under the volatile runtime directory and runs
Samba validation against that candidate. The candidate removes only the SimpleSaferServer global and
shares include marker blocks, so shares loaded from other administrator-owned include files are
still detected. If Samba cannot produce the effective config, share create and rename paths fail
closed instead of guessing whether a name is safe.

## Manual Conversion: Unmanaged Share to SimpleSaferServer-Managed Share

Only convert a share if it can fit the supported SimpleSaferServer-managed format.
If the share depends on unsupported Samba directives, leave it unmanaged and maintain it manually.

### Conversion Steps

1. Back up `/etc/samba/smb.conf` and `/etc/samba/simple_safer_server_shares.conf`.
2. Find the unmanaged share block or include file that defines the share you want to convert.
3. Remove it from the unmanaged config source and add it to `/etc/samba/simple_safer_server_shares.conf`.
4. Keep only the supported share settings.
5. Restart Samba.
6. Reload the Network File Sharing page and confirm the share appears in the managed table.

### Example

Suppose you currently have this unmanaged share:

```ini
[backup]
   path = /media/backup
   writeable = Yes
   comment = Backup share
   valid users = admin
```

Move it to `/etc/samba/simple_safer_server_shares.conf` as:

```ini
[backup]
   path = /media/backup
   writeable = Yes
   create mask = 0777
   directory mask = 0777
   public = no
   comment = Backup share
   valid users = admin
```

Then restart Samba.
Restarting Samba disconnects anyone who is currently connected to a share, so active file copies or other SMB activity will drop:

```bash
sudo systemctl restart smbd nmbd wsdd2
```

Reload the Network File Sharing page after that.

## Setup Wizard Behavior

During setup, SimpleSaferServer tries to create or refresh the default `backup` share using the same ownership-aware SMB logic as the main UI.

If an Unmanaged Samba Share named `[backup]` already exists anywhere Samba loads it:

- setup does not overwrite it
- setup reports `Samba share "backup" already exists. Rename or remove it, then retry.`
- the user must either rename/remove that unmanaged share manually or convert it into the SimpleSaferServer shares file first

This is intentional. Ownership by share name alone is not safe enough.

## Uninstall Behavior

The uninstaller removes the SimpleSaferServer include blocks from `smb.conf` when the main config
can be safely rewritten. It deletes the SimpleSaferServer-owned Samba include files independently,
including when `smb.conf` is missing or its SimpleSaferServer marker blocks are malformed.

It does not remove:

- unmanaged share blocks
- unrelated Samba configuration
- shared packages or services such as Samba, `wsdd2`, Python, or rclone

That means manually maintained Samba shares survive uninstall unless they were moved into
`/etc/samba/simple_safer_server_shares.conf`.

## Operational Notes

- The page still shows Samba service status for the whole system, not just SimpleSaferServer-managed shares.
- The folder picker only helps choose a filesystem path. It does not validate advanced Samba semantics.
- If you manually edit a SimpleSaferServer-managed share, keep it as a normal share section in
  `/etc/samba/simple_safer_server_shares.conf`; unsupported directives may be overwritten by later
  Web UI edits.
