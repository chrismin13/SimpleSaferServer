# PiVPN

SimpleSaferServer has a read-only PiVPN page at `/pivpn`.

The page is meant to help an admin see whether PiVPN looks present on the server and whether the common WireGuard or OpenVPN systemd services are running. It also shows common PiVPN commands that can be copied into a root terminal.

## What The Page Shows

- Whether the `pivpn` command is available to the web service.
- The status of `wg-quick@wg0.service`, which is the common WireGuard unit used by PiVPN.
- The status of common OpenVPN units: `openvpn@server.service` and `openvpn.service`.
- Copyable commands for listing, adding, removing, and debugging PiVPN clients.

## What The Page Does Not Do

The page does not add, remove, or edit VPN clients from the browser.

That is intentional. PiVPN already provides terminal tools for those jobs, and adding browser-side VPN management would need more careful handling of profile files, QR codes, and client secrets.

## Useful Terminal Commands

Run these on the server:

```bash
pivpn -c
pivpn -a
pivpn -r
pivpn -d
```

Use `sudo` first if your shell is not already running as root.

## PiVPN Documentation

Use the official PiVPN docs for installation and VPN-specific setup:

`https://docs.pivpn.io/`
