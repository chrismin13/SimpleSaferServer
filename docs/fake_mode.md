# Fake Mode

Fake mode is for local development, demos, and hosted previews where the app cannot use the real
Debian machine environment.

## What Fake Mode Simulates

Fake mode avoids local system changes that would be disruptive or unavailable on a development
machine:

- systemd service and timer state
- local disks and backup-drive mount state
- Samba service state and managed Samba configuration
- restart, shutdown, and other destructive machine actions
- writes to real `/etc` paths

The default fake-mode data directory is `.dev-data/`. `run_fake.sh` starts the app with
`SSS_MODE=fake` and enables auto-login by default. Set `SSS_SKIP_LOGIN=false` to use the normal
login screen. `reset_fake_mode.sh` deletes `.dev-data/` so setup can be run again from a clean
state.

## External Providers

Fake mode is not an external-provider sandbox. DDNS and cloud-backup integrations may still contact
real providers when real credentials and destinations are configured. That is intentional: fake mode
should stay close enough to real behavior that provider bugs can be reproduced during development.

Use disposable domains, test subdomains, scoped Cloudflare tokens, and test cloud destinations when
exercising provider behavior from fake mode.

## State And Persistence

Fake-mode config, users, secrets, logs, and simulated machine state live under `.dev-data/` unless
`SSS_DATA_DIR` points somewhere else. Operational state that does not need to survive a restart can
use the runtime volatile directory.

Railway demos run fake mode with `SSS_DATA_DIR=/data`, so `/data` must be a persistent Railway
volume if setup state should survive redeploys.
