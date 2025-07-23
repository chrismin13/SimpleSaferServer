# SimpleSaferServer: Comprehensive Design Q&A

This document provides detailed answers to key design questions about the SimpleSaferServer codebase, organized by architectural, workflow, scheduling, data, error handling, security, performance, extensibility, design deviation, and use-case traceability topics.

---

## 1. Architectural Overview

**Q: What are the major software components and how are they organized (e.g., UI, service layer, storage layer)?**
A: The system is organized into:
- **Web UI**: Flask-based web interface (`app.py`, `templates/`, `static/`)
- **Service Layer**: Python modules for configuration, user, and SMB management (`config_manager.py`, `user_manager.py`, `smb_manager.py`, `system_utils.py`)
- **Background Jobs**: Systemd services/timers and shell/Python scripts for backup, health checks, and cloud sync (`scripts/`, systemd units)
- **Storage Layer**: Local disk (mounted at `/media/backup`), cloud storage (via rclone/MEGA), and configuration/log files in `/etc/SimpleSaferServer` and `/var/log/SimpleSaferServer`
- **ML Model**: XGBoost model for drive health prediction (`harddrive_model/`)

**Q: What are the main communication mechanisms between components (e.g., REST, WebSocket, CLI invocations)?**
A: Communication is via:
- HTTP(S) requests to Flask endpoints (UI <-> backend)
- Flask-SocketIO for live updates
- Systemd for scheduling and running jobs
- CLI invocations of scripts (Bash, Python)
- File-based config/log sharing

**Q: Which components run as long-lived services vs one-shot jobs?**
A:
- **Long-lived**: Flask web server (`simple_safer_server_web.service`)
- **One-shot**: Backup, health check, and mount check jobs (`check_mount.service`, `check_health.service`, `backup_cloud.service`)

**Q: What are the dependencies between services (e.g., UI depends on stats collector)?**
A: The UI depends on the background jobs for up-to-date status and logs. Health checks and mount checks must succeed for backups to run. The ML model is required for health checks.

**Q: Is there an architecture diagram or clear code layout that maps each module/file to its role?**
A: See the README and this document for a mapping. Key files:
- `app.py`: Main Flask app
- `config_manager.py`: Config and secret management
- `user_manager.py`: User and auth management
- `smb_manager.py`: Samba/SMB management
- `system_utils.py`: System-level utilities
- `scripts/`: Backup, health, and alert scripts
- `harddrive_model/`: ML model files

---

## 2. Workflow Narratives & Diagrams

**Q: What are the high-level workflows executed by the system?**
A: Main workflows:
- Initial setup (admin, drive, backup, email, schedule)
- Scheduled local backup
- Scheduled cloud backup
- Drive health monitoring
- User management
- Network file sharing
- Recovery from backup

**Q: What sequence of components/functions is involved in onboarding a new system?**
A:
1. User accesses `/setup` (Flask route)
2. Steps: Admin account → Drive format/mount → Backup config → Email setup → Schedule
3. Config saved to `/etc/SimpleSaferServer/config.conf`
4. Systemd services/timers and scripts installed

**Q: How is a nightly local backup performed from start to finish?**
A:
1. `check_mount.timer` triggers `check_mount.service` (mount check)
2. `check_health.timer` triggers `check_health.service` (health check)
3. `backup_cloud.timer` triggers `backup_cloud.service` (cloud backup)
4. Each step logs alerts and sends emails on failure

**Q: What is the sequence from SMART data polling to alerting the user via email?**
A:
1. `check_health.sh` runs, collects SMART data
2. Calls `predict_health.py` (ML model)
3. If unhealthy, sends email via msmtp and logs alert

**Q: How does a cloud sync job begin and what determines its timing?**
A: Triggered by `backup_cloud.timer` (systemd, time set in config). Can also be run manually from the UI.

**Q: What actions are triggered when a drive is flagged as failed?**
A: Email alert sent, alert logged, backup job may be skipped or marked as failed.

**Q: What sequence is followed during a recovery from a backup?**
A: User mounts backup drive, restores files manually or via provided instructions (no automated restore workflow in codebase).

---

## 3. Scheduling & Orchestration

**Q: What are all the systemd timer units defined in the codebase?**
A:
- `check_mount.timer` → `check_mount.service`
- `check_health.timer` → `check_health.service`
- `backup_cloud.timer` → `backup_cloud.service`
- `simple_safer_server_web.service` (web UI, long-lived)

**Q: What services are they triggering and at what intervals?**
A: Intervals are set in `/etc/SimpleSaferServer/config.conf` (default: daily at 3:00 AM for backup, health/mount checks just before). Timers are created/updated by the setup wizard and config changes.

**Q: How are failures handled in scheduled tasks?**
A: Failures trigger email alerts (via msmtp) and are logged to `/etc/SimpleSaferServer/alerts.json` using `log_alert.py`.

**Q: Are there hard dependencies enforced between timers?**
A: Timers are scheduled sequentially (mount check → health check → backup), but not strictly enforced; each job checks preconditions (e.g., drive mounted).

**Q: Is there a startup sequence or init routine on system boot?**
A: Yes, systemd starts the web UI and timers on boot. Mounting and health checks are performed before backup jobs.

**Q: How are race conditions avoided between concurrently running tasks (e.g., SMART scan + rclone)?**
A: Sequential timer scheduling and pre-checks in scripts reduce risk. No explicit locking, but jobs are short-lived and run in order.

---

## 4. Data & Configuration Model

**Q: Where is the main configuration stored (file paths, format)?**
A: Main config: `/etc/SimpleSaferServer/config.conf` (INI format). Secrets: `/etc/SimpleSaferServer/.secrets` (JSON, encrypted). Alerts: `/etc/SimpleSaferServer/alerts.json` (JSON).

**Q: What is the schema for the YAML configuration files?**
A: No YAML; uses INI for config, JSON for secrets/alerts/users.

**Q: Where and how are logs stored (e.g., for SMART, rsync, rclone)?**
A: Web UI logs: `/var/log/SimpleSaferServer/app.log`. Alerts: `/etc/SimpleSaferServer/alerts.json`. Systemd jobs log to journal (`journalctl -u <service>`). Samba logs: `/var/log/samba/`.

**Q: What is the structure and format of the serialized ML model?**
A: XGBoost model (`harddrive_model/xgb_model.json`) and threshold (`optimal_threshold_xgb.pkl`) are stored in `/opt/SimpleSaferServer/harddrive_model/` after install.

**Q: Where are user-defined backups stored and how is retention handled?**
A: Local backups are on the mounted drive (default `/media/backup`). Cloud backups are in the configured rclone/MEGA remote. Retention is managed externally (no built-in pruning).

**Q: How are job results persisted between runs?**
A: Status and logs are available via systemd journal and alerts. No persistent job history beyond logs/alerts.

---

## 5. Error Handling & Recovery

**Q: How are errors caught and reported during each type of job?**
A: Bash/Python scripts catch errors, send email via msmtp, and log alerts using `log_alert.py`. Flask app logs errors to `/var/log/SimpleSaferServer/app.log`.

**Q: Are logs or alerts generated automatically for failures?**
A: Yes, all critical failures in jobs/scripts generate alerts and send emails if configured.

**Q: What happens when a backup partially fails?**
A: The job is marked as failed, an alert is logged, and an email is sent. No automatic retry, but user is notified.

**Q: Is there a retry mechanism for failed syncs or drive scans?**
A: No built-in retry; jobs run on the next scheduled interval or can be triggered manually.

**Q: What indicators mark a system or job as "healthy" vs "faulted"?**
A: Health is determined by SMART/ML model results. Job status is shown in the dashboard and via alerts.

**Q: How does the system recover from partial configuration or disk errors?**
A: User intervention is required. Alerts and logs guide the user to resolve issues (e.g., remount drive, fix config).

---

## 6. Security & Permissions

**Q: What authentication/authorization model is used for the web interface?**
A: Admin login required for all management actions. Only admin users can access the UI. Sessions managed by Flask.

**Q: Are admin credentials stored securely?**
A: Yes, hashed with Werkzeug and stored in `/etc/SimpleSaferServer/users.json` (permissions 0600, directory 0700).

**Q: How is Samba configured in terms of access control?**
A: Samba users are synced with system users. Shares are restricted to allowed users. Config managed by `smb_manager.py`.

**Q: Where are credentials for msmtp and rclone stored, and how are they protected?**
A: msmtp config is written to `/etc/msmtprc` (0600). rclone config is in `~/.config/rclone/rclone.conf` (0600). MEGA passwords are obscured and stored in config.

**Q: Is the web interface accessible over HTTPS, and how is the certificate handled?**
A: By default, the Flask app runs on HTTP. HTTPS can be set up externally (e.g., with a reverse proxy).

**Q: Are there safeguards against unauthorized local access?**
A: Sensitive files are permissioned (0600/0700). No explicit local access controls beyond OS permissions.

---

## 7. Performance Considerations

**Q: What are the typical system requirements for running this service?**
A: Designed for low-power devices (e.g., Raspberry Pi). Requires Python 3, Flask, XGBoost, rclone, Samba, msmtp, smartmontools.

**Q: Are there performance benchmarks for local vs cloud sync?**
A: No formal benchmarks in codebase. Performance depends on hardware and network.

**Q: What I/O or CPU limitations have been observed on Raspberry Pi?**
A: Not explicitly documented, but heavy backup/ML jobs may be slow on low-end hardware.

**Q: Is concurrency limited intentionally to avoid resource contention?**
A: Jobs are scheduled sequentially. No explicit concurrency controls, but systemd timers avoid overlap.

**Q: How is bandwidth throttling configured in rclone?**
A: Via the `bandwidth_limit` config, passed as `--bwlimit` to rclone in `backup_cloud.sh`.

**Q: Are any background services prioritized differently in systemd?**
A: No explicit priority settings; all jobs run as root with default priorities.

---

## 8. Extensibility & Future-Proofing

**Q: Are there documented or implicit hooks for supporting additional cloud storage backends?**
A: Yes, via rclone advanced config. Any rclone-supported backend can be used.

**Q: Could support for multi-disk arrays (e.g., RAID, ZFS) be added in the future?**
A: Not currently supported, but could be added by extending mount/config logic.

**Q: How modular are the backup/sync routines for replacing rsync/rclone with alternatives?**
A: Backup logic is in scripts; could be swapped by editing scripts and systemd units.

**Q: Is the ML component modular enough to support retraining or replacement models?**
A: Yes, the XGBoost model can be retrained and replaced. Model files are loaded at runtime.

**Q: Is the logging system designed to support external aggregation?**
A: Not directly, but logs are in standard files and systemd journal, so external aggregation is possible.

---

## 9. Design Deviations from Proposal

**Q: Which originally planned features were dropped or trimmed?**
A: No explicit stubs/TODOs for dropped features, but no automated restore workflow is present.

**Q: Which features were simplified during implementation?**
A: Recovery is manual, not automated. Only basic health prediction is implemented.

**Q: Which designs were modified due to performance or security trade-offs?**
A: Uses systemd and shell scripts for reliability and simplicity. Credentials are stored with strong permissions.

**Q: Were any external library dependencies added or removed for feasibility reasons?**
A: Uses system packages for Python dependencies to avoid pip conflicts. rclone is installed via official script for full backend support.

**Q: Are there stubs or TODOs left in the code suggesting postponed features?**
A: No major stubs/TODOs found in main codebase.

---

## 10. Use-Case Traceability

**Q: For each main user scenario, what components and interactions are involved?**
A:
- **Setup**: UI (Flask) → ConfigManager → SystemUtils
- **Backup**: systemd timer → shell script → rclone → alert/email
- **Health Check**: systemd timer → shell script → ML model → alert/email
- **User Management**: UI → UserManager → users.json
- **Network Sharing**: UI → SMBManager → Samba config

**Q: In a drive failure + restore scenario, how does the system detect failure, alert the user, and allow recovery?**
A: Health check job detects failure (SMART/ML), logs alert, sends email. User is guided to replace/restore drive manually.

**Q: In a backup configuration flow, what stages and validation steps are involved?**
A: UI validates input, saves to config, updates systemd timers/services, and tests credentials/paths.

**Q: How does the system track state across sessions to ensure continuity?**
A: State is persisted in config files and user database. Job status is tracked via logs and alerts.

**Q: Are there any user activity logs or histories stored to trace past events?**
A: User login times are stored in `users.json`. Alerts and job logs provide event history.

---

_End of document._ 