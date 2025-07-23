# Dashboard

The **Dashboard** provides a single page overview of system state and the controls you’ll use most often.

---

## 1. Status Cards

| Card | Information Shown |
|------|-------------------|
| **Storage** | Drive connection status, used / total space and percentage used. |
| **Network File Sharing (SMB)** | Whether Samba services are running. |
| **Hard-Drive Health** | Health badge (Healthy / Warning), predicted failure risk, current temperature. |
| **System Resources** | Live CPU load, RAM usage, network up/down speeds. |

Values refresh automatically; no page reload required.

---

## 2. Task Schedule

The **Task Schedule** table lists all automated jobs installed by SimpleSaferServer.

| Column | Purpose |
|--------|---------|
| Task | Name (click to view logs). |
| Next Run | When the job will run next. |
| Last Run | Time the job last finished. |
| Ran For | Duration of the last run. |
| Status | Current state: Success, Running, Failure, Not Run Yet, Missing, Error. |
| Actions | `Run Now` executes the task immediately. |

Press **Refresh** to reload the table at any time.

---

## 3. System Actions

| Button | Function |
|--------|----------|
| **Unmount Storage** | Safely unmounts the backup drive and stops related services. You can use this if you wish to remove the USB drive for any reason. |
| **Mount Storage** | Mounts the drive and re-enables services if they were stopped. |
| **Restart System** | Performs a standard reboot. |
| **Shutdown System** | Powers the system off. |

Each action opens a confirmation dialog that shows progress and any errors