# Server Identity Hostname

## Context

The setup wizard collected `system.server_name`, but that value was only stored in
SimpleSaferServer config and used by alert email scripts. Operators expected the
same name to also be the server name they connect to on the network.

## Decision

Server-name changes now go through a shared server-identity service. The service
validates one simple hostname format, updates `/etc/hosts`, applies the OS
hostname, persists SimpleSaferServer config, and restarts Samba discovery/services
when changed after setup.

The original hostname is recorded once so uninstall can warn operators that the
host-level name was changed by SimpleSaferServer. Uninstall intentionally leaves
the current hostname and `/etc/hosts` in place because they are host identity, not
app-owned files.

## Follow-up Checks

- Setup and File Sharing should keep using the shared validation and helper text.
- If hostname policy changes, update the Python service, setup JavaScript, and
  File Sharing JavaScript together.
- `uninstall.sh` should continue warning about managed hostname metadata before
  deleting `/etc/SimpleSaferServer`.
