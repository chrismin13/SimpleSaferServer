# Network File Sharing

The Network File Sharing page manages Samba shares and Samba service status.

SimpleSaferServer now distinguishes between two kinds of Samba shares:

- **SimpleSaferServer-managed shares**: share blocks wrapped with explicit SimpleSaferServer ownership markers in `smb.conf`
- **Unmanaged shares**: any non-system Samba share blocks that exist in `smb.conf` without those markers

That ownership split matters because SimpleSaferServer only edits shares that it can identify safely.

## What the Page Shows

- **Managed shares table**: lists only SimpleSaferServer-managed shares
- **Add Share**: creates a new SimpleSaferServer-managed share
- **Edit Share**: updates a SimpleSaferServer-managed share
- **Delete Share**: removes a SimpleSaferServer-managed share
- **Unmanaged share warning**: appears when SimpleSaferServer detects other non-system Samba shares in `smb.conf`
- **Restart Services**: restarts `smbd` and `nmbd`
  Restarting Samba disconnects anyone who is currently connected to a share, so active file copies or other SMB activity will drop.

If unmanaged shares are detected, the page shows a small warning button with the count.
That button opens a modal that:

- lists the unmanaged share names
- explains that SimpleSaferServer will not edit or remove them
- links to this document for manual conversion guidance

## SimpleSaferServer-Managed Share Format

A SimpleSaferServer-managed share uses wrapper comments like this:

```ini
# BEGIN SimpleSaferServer share: backup
[backup]
   path = /media/backup
   writeable = Yes
   create mask = 0777
   directory mask = 0777
   public = no
   comment = Default backup share created by SimpleSaferServer setup
   valid users = admin
# END SimpleSaferServer share: backup
```

Those wrapper comments are the ownership markers.
They are what let SimpleSaferServer:

- show only its own shares in the editable table
- update only the shares it owns
- delete only the shares it owns
- remove only its managed share blocks during uninstall

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

An unmanaged share may contain Samba options that the SimpleSaferServer UI does not understand.
If the app tried to import and rewrite those blocks automatically, it could silently remove or change settings that still matter.

SimpleSaferServer therefore takes the safer path:

- detect unmanaged shares
- warn the user that they exist
- leave them active in Samba
- refuse to edit or remove them

## Manual Conversion: Unmanaged Share to SimpleSaferServer-Managed Share

Only convert a share if it can fit the supported SimpleSaferServer-managed format.
If the share depends on unsupported Samba directives, leave it unmanaged and maintain it manually.

### Conversion Steps

1. Back up `/etc/samba/smb.conf`.
2. Find the unmanaged share block that you want to convert.
3. Replace it with the SimpleSaferServer-managed wrapper format.
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

Convert it to:

```ini
# BEGIN SimpleSaferServer share: backup
[backup]
   path = /media/backup
   writeable = Yes
   create mask = 0777
   directory mask = 0777
   public = no
   comment = Backup share
   valid users = admin
# END SimpleSaferServer share: backup
```

Then restart Samba.
Restarting Samba disconnects anyone who is currently connected to a share, so active file copies or other SMB activity will drop:

```bash
sudo systemctl restart smbd nmbd
```

Reload the Network File Sharing page after that.

## Setup Wizard Behavior

During setup, SimpleSaferServer tries to create or refresh the default `backup` share using the same ownership-aware SMB logic as the main UI.

If an unmanaged share named `[backup]` already exists:

- setup does not overwrite it
- setup reports a clear error
- the user must either remove that unmanaged share manually or convert it into the SimpleSaferServer-managed format first

This is intentional. Ownership by share name alone is not safe enough.

## Uninstall Behavior

The uninstaller removes only marker-wrapped SimpleSaferServer-managed share blocks from `/etc/samba/smb.conf`.

It does not remove:

- unmanaged share blocks
- legacy untagged share blocks
- unrelated Samba configuration

That means older or manually maintained Samba shares survive uninstall unless they have been converted into the marker-wrapped SimpleSaferServer-managed format.

## Operational Notes

- The page still shows Samba service status for the whole system, not just SimpleSaferServer-managed shares.
- The folder picker only helps choose a filesystem path. It does not validate advanced Samba semantics.
- If you manually edit a SimpleSaferServer-managed share block, keep the wrapper markers and the supported field set intact so the app can still recognize it later.
