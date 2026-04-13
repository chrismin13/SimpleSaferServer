# Railway Deployment Notes

Railway is a cloud hosting platform that can build and run this repository
directly from GitHub.

SimpleSaferServer runs in fake mode on Railway on purpose. Railway cannot
provide the local disks, Samba services, or systemd environment that the full
Debian install uses, so the demo stores its writable state in a Railway volume
instead.

Regular SimpleSaferServer users do not need any of this. This document is only
for development and demo hosting on Railway.

If you are installing SimpleSaferServer on a real Debian-based machine, use the
normal install flow instead:

- [README.md](../README.md)
- [manual_install.md](manual_install.md)

## Deploy Checklist

Run these steps from the root of the `SimpleSaferServer` repository.

1. Open the Railway project and select the `SimpleSaferServer` service.

2. Create a persistent volume and attach it to that service.

3. Mount the volume at `/data`.

4. Deploy the repository from the repo root.

5. Open the app and complete setup once.

6. Redeploy one more time to confirm the setup still exists.

If setup is still there after step 6, the deployment is correct.

## CLI Version Of The Same Flow

`railway up` uploads the files from your current local checkout, so run it from
the root of the repository state you actually want to deploy.

```bash
cd /path/to/SimpleSaferServer
railway status
railway volume list
railway volume add --mount-path /data
railway up
```

After the deploy finishes, run this once to verify the volume exists:

```bash
railway volume list
```

## What Must Persist

The writable state lives under the fake-mode data directory. That includes:

- `config/config.conf`
- `config/users.json`
- `config/.secrets`
- `config/.key`
- `config/.flask-secret-key`
- logs and fake task state

The repo sets `SSS_DATA_DIR=/data` in `nixpacks.toml`, so `/data` must be a
real Railway volume. If no volume is attached, `/data` is only a normal
container directory and every deploy starts from an empty filesystem again.

## Notes

- The app now persists the Flask session secret in the writable config
  directory unless `FLASK_SECRET_KEY` is set explicitly. That keeps login
  cookies stable across deploys when the volume persists.
- If you ever mount the Railway volume somewhere other than `/data`, the app
  prefers Railway's `RAILWAY_VOLUME_MOUNT_PATH` variable automatically.
