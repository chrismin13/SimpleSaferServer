# Tailscale

The Tailscale page shows how this server looks from Tailscale.

It is a read-only page. SimpleSaferServer does not install Tailscale, log in to a
tailnet, change ACLs, or edit Tailscale settings.

## What The Page Shows

- **Connection**: whether the `tailscale` command reports a connected server
- **Host**: the server name reported by Tailscale
- **MagicDNS Names**: Tailscale DNS names such as `server.tailnet.ts.net`
- **Access URLs**: Web UI URLs using MagicDNS names and Tailscale IP addresses
- **Details**: the raw DNS names and Tailscale IP addresses found in
  `tailscale status --json`

The Web UI still listens on port `5000`, so Tailscale URLs use that same port.

## When Nothing Shows Up

If the page says Tailscale is not installed, install and configure Tailscale on
the server outside SimpleSaferServer.

If Tailscale is installed but not connected, log in with the normal Tailscale
tools and then refresh the page.

## Installer Output

At the end of installation, the installer still prints local IPv4 Web UI URLs.
When Tailscale is already installed and connected, it also prints Tailscale
MagicDNS and Tailscale IP Web UI URLs.
