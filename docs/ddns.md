# Dynamic DNS

Dynamic DNS keeps public DNS records pointed at the server's current public IPv4 address. The `DDNS Update` task can run on schedule from systemd or immediately from the Dashboard task controls.

## Fake Mode Behavior

Fake mode simulates local system services, disks, Samba, and destructive machine actions. It does not sandbox DDNS provider APIs. If DuckDNS or Cloudflare is enabled with valid credentials, saving the DDNS settings or manually forcing a sync can update live DNS records.

Use a disposable test domain, test subdomain, or scoped Cloudflare token when testing DDNS provider behavior from fake mode.

## Providers

- **DuckDNS** updates the configured DuckDNS domain. When SimpleSaferServer cannot detect a public IPv4 address, DuckDNS can still use its own automatic IP detection.
- **Cloudflare** updates an existing `A` record in the configured zone. Cloudflare requires the public IPv4 address from SimpleSaferServer, so the Cloudflare update fails if that address cannot be detected.

## Task Status

The updater writes provider details to `ddns_status.json` before it exits. If any enabled provider reports `Error` or `Configuration Missing`, the task exits with a failure code so systemd and the Dashboard show the `DDNS Update` run as failed while the DDNS page still has the specific provider message.

## Cloudflare Proxy Mode

Cloudflare proxy mode is off by default. Leave it off for typical home-network DDNS, especially when the DNS name points to services such as WireGuard, SSH, game servers, media servers, or any custom TCP/UDP port. In that mode Cloudflare acts as DNS only, so clients connect directly to the public IP address in the `A` record.

Turn proxy mode on only when the record should serve Cloudflare-supported web traffic through the orange-cloud proxy. When proxy mode is enabled, Cloudflare receives the incoming traffic first and only forwards protocols and ports that its proxy supports. Unsupported services can stop working even though the DNS record itself resolves.

Cloudflare documents this behavior in its [proxy status](https://developers.cloudflare.com/dns/proxy-status/) and [DNS proxy use case](https://developers.cloudflare.com/dns/proxy-status/use-cases/) guides.

The Cloudflare proxy toggle controls the record's orange-cloud setting. The updater checks both the existing record IP address and the existing proxy state before deciding that no update is needed, because changing only the proxy setting still requires a DNS record update.

When proxy mode is enabled, SimpleSaferServer sends Cloudflare `ttl: 1`, which is Cloudflare's automatic TTL value for proxied records. When proxy mode is disabled, SimpleSaferServer sends `ttl: 3600`.

## Required Cloudflare Setup

1. Create the `A` record in Cloudflare before enabling the updater.
2. Copy the zone identifier from the Cloudflare domain overview page.
3. Create a scoped API token using Cloudflare's DNS edit permissions for the selected zone.
4. Enter the full DNS record name, such as `server.example.com`, in SimpleSaferServer.
