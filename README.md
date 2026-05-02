# SimpleSaferServer

> [!TIP]
> ** Want to see it in action?**  
> Check out the [Live Management Demo](https://sssdemo.chrismin13.com) to explore the dashboard and features in a simulated environment!

SimpleSaferServer is my vibe-coded experimentation project for helping with backing up your files on your home or small-business server using a 3-2-1 backup strategy. Over time, I have been working towards adding all the features and services that I would want in my own server when I set up from scratch, as well as experimenting with the latest hotness in vibe coding at that period in time. 

I always try to keep the project as stable as possible, especially in the main branch, but the whole point of it is to be fun and experimental. I will try out new things and add things that I mostly care about for my use case. If you see this works for you, you are more than welcome to install it for your own server at your own risk! I will be happy to help you out if you run into issues.

## Quick Installation

To install SimpleSaferServer on a clean Debian or Ubuntu based system, run the following command:

```bash
curl -fsSL https://sss.chrismin13.com/install.sh | sudo bash
```

- This script will install all dependencies, set up the service, and print your Web UI address.
- The management Web UI is accessible only by Administrators. The first account created during setup becomes the initial administrator.
- For more details and the maintained documentation index, visit the [documentation section on the website](https://sss.chrismin13.com/#documentation).
- For more install options, see the [Installation Guide](docs/install.md) or  the [Manual Installation Guide](docs/manual_install.md) if you want to install manually.

---

## 🗑️ Uninstallation

To completely remove SimpleSaferServer from your system, you can:

**If you still have the repository folder:**
```bash
cd /path/to/SimpleSaferServer
sudo bash uninstall.sh
```

**Or, run directly from the web (recommended):**
```bash
curl -fsSL https://sss.chrismin13.com/uninstall.sh | sudo bash
```

This will:
- Remove all installed scripts, models, and application files
- Remove the systemd service and background tasks
- Clean up SimpleSaferServer configuration, logs, user data, and the managed `/etc/fstab` entry
- Remove the Samba users synced from SimpleSaferServer accounts
- Remove marker-wrapped SimpleSaferServer-managed Samba share blocks from `/etc/samba/smb.conf`

This does not remove shared system packages such as Samba, Python, or rclone.
Unmanaged or legacy untagged Samba share blocks are left in `/etc/samba/smb.conf` for safety.
See the [Uninstallation Guide](docs/uninstall.md) for details.

**Note:** This process is irreversible. Back up any important data before uninstalling.

---

## Local Fake Mode (for testing without installing!)

Fake mode is helpful when you want to test the app without installing it. This is great for development, or for trying out the app before using it on a real server.

To run the app locally without touching system services, disks, or `/etc`, start it in fake mode:

```bash
bash install_dev.sh
bash run_fake.sh
```

To wipe fake-mode setup state and start over:

```bash
bash reset_fake_mode.sh
```

Fake mode should work for most Linux distributions.

- Fake mode stores its state under `.dev-data/`.
- Fake mode simulates local system services, disks, Samba, and destructive machine actions. Be careful, many features will still work, such as DDNS and Cloud Backup! This is done in order to help with developing new features and debugging the application.
- `reset_fake_mode.sh` deletes `.dev-data/` so you can rerun setup from a clean fake-mode state, and bring you back to the Setup wizard.
- `run_fake.sh` enables fake-mode auto-login by default. Set `SSS_SKIP_LOGIN=false` if you want the normal login screen.
- See [Fake Mode](docs/fake_mode.md) for the full development and provider-integration behavior.

## Development

SimpleSaferServer keeps application compatibility for older Python runtimes, down to Debian 10 / Python 3.7 and Ubuntu 20.04 / Python 3.8, but the strict security-supported development baseline is Debian 13 / Python 3.13. Development conventions, architecture rules, and quality commands live in [docs/development.md](docs/development.md).

Set up local development tooling with:

```bash
bash install_dev.sh
.venv/bin/pre-commit install
```

The pre-commit hooks are intentionally fast and only cover ruff formatting/linting. Run the strict
local check suite when you want a pre-push check:

```bash
bash check_ci.sh
```

To reproduce both GitHub Actions lanes in Docker, run:

```bash
bash check_ci_docker.sh
```

To run only one lane, pass the lane name:

```bash
bash check_ci_docker.sh python313-security
bash check_ci_docker.sh python37-legacy-compat
```

---

# Documentation

If you're looking for more info, the website keeps the most up-to-date documentation index in one place:

- [Documentation Index](https://sss.chrismin13.com/#documentation)

The underlying markdown files still live in [`docs/`](docs/). Start with [install.md](docs/install.md) for normal installation or [manual_install.md](docs/manual_install.md) for the manual path.

