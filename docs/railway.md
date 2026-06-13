# Railway Deployment Notes

Railway is a cloud hosting platform that can build and run this repository
directly from GitHub.

SimpleSaferServer runs in fake mode on Railway on purpose. Railway cannot
provide the local disks, Samba services, or systemd environment that the full
Debian install uses, so the demo stores its writable state in a Railway volume
instead.

Fake mode is a local-system simulation, not a sandbox for outside APIs. DDNS can
still contact real providers if valid credentials are configured. The trimmed
Railway demo does not install `rclone`, so Cloud Backup provider setup, folder
listing, and backup runs are not supported there unless you intentionally add
`rclone` back to the Railway image. See [Fake Mode](fake_mode.md).

Regular SimpleSaferServer users do not need any of this. This document is only
for development and demo hosting on Railway.

If you are installing SimpleSaferServer on a real Debian-based machine, use the
normal install flow instead:

- [README.md](../README.md)
- [install.md](install.md)

## Deploy Checklist

Run these steps from the root of the `SimpleSaferServer` repository.

1. Open the Railway project and select the `SimpleSaferServer` service.

2. Set these service variables:

   ```text
   SSS_MODE=fake
   SSS_SKIP_LOGIN=true
   SSS_DATA_DIR=/data
   WEB_THREADS=4
   ```

3. Create a persistent volume and attach it to that service.

4. Mount the volume at `/data`.

5. Deploy the repository from the repo root.

6. Open the app and complete setup once.

7. Redeploy one more time to confirm the setup still exists.

If setup is still there after step 7, the deployment is correct.

## What Railway Builds

Railway uses `railway.toml` to select Railpack and start Gunicorn. Railpack reads
the Python project files in this repository:

- `.python-version` selects Python 3.14.
- `pyproject.toml` lists the runtime Python packages.
- `uv.lock` pins the exact Python dependency versions.

Railway does not run `install.sh`. That is intentional. The full installer is
for real Debian or Ubuntu hosts where SimpleSaferServer manages local disks,
Samba, systemd timers, mail alerts, HDSentinel, and cloud-backup tooling.

The Railway fake-mode demo skips those host packages:

- Samba and `wsdd2`
- `smartmontools` and HDSentinel
- `msmtp`
- `rclone`
- disk tools such as `fdisk`, `ntfs-3g`, and `rsync`
- unattended-upgrades and other real APT automation

Most pages still work because fake mode stores simulated machine state under
`/data`. Cloud Backup is the main exception because its provider actions call
the real `rclone` binary.

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

Set `SSS_DATA_DIR=/data` in Railway service variables, and make `/data` a real
Railway volume. If no volume is attached, `/data` is only a normal container
directory and every deploy starts from an empty filesystem again.

## Notes

- The app now persists the Flask session secret in the writable config
  directory unless `FLASK_SECRET_KEY` is set explicitly. That keeps login
  cookies stable across deploys when the volume persists.
- If you ever mount the Railway volume somewhere other than `/data`, the app
  prefers Railway's `RAILWAY_VOLUME_MOUNT_PATH` variable automatically.
