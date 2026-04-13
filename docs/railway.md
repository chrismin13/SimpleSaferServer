# Railway Deployment Notes

SimpleSaferServer runs in fake mode on Railway on purpose. That keeps the live
demo safe because Railway cannot provide the local disks, Samba services, or
systemd environment that the full Debian install uses.

## Why setup resets without a volume

In Railway fake mode, the app stores its writable state under the fake-mode data
directory. That includes:

- `config/config.conf`
- `config/users.json`
- `config/.secrets`
- `config/.key`
- `config/.flask-secret-key`
- logs and fake task state

The repo config sets `SSS_DATA_DIR=/data` in `nixpacks.toml`. If Railway does
not have a persistent volume attached, `/data` is only a normal container
directory, so every deploy starts from an empty filesystem again.

## How to keep config across deploys

1. Create a Railway volume for the service.
2. Attach it to the `SimpleSaferServer` service.
3. Mount it at `/data`, or mount it somewhere else and let the app use
   Railway's `RAILWAY_VOLUME_MOUNT_PATH` runtime variable automatically.
4. Redeploy once after the volume is attached.

Useful CLI checks:

```bash
railway status
railway volume list
railway volume add --mount-path /data
```

If you create the volume with a different mount path later, the app now prefers
`RAILWAY_VOLUME_MOUNT_PATH` over the default `/data` setting so the writable
state still follows the real attached volume.

## Session behavior

The app now persists its Flask session secret inside the writable config
directory unless `FLASK_SECRET_KEY` is set explicitly. That keeps login cookies
stable across deploys when the Railway volume persists.

If there is no volume, both configuration and session state remain disposable.
