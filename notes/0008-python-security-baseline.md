# 0008 Python Security Baseline

## Summary

- Split dependency policy into a Debian 13 / Python 3.13 security-supported baseline and a Debian 10 / Python 3.7 compatibility lane.
- Keep Python 3.7 syntax and runtime checks because some operators may still be on Debian 10, but stop treating that lane as dependency-audit clean.

## Rules / Constraints

- Preserve Python 3.7 compatibility for Debian 10 application code.
- Keep strict dependency auditing on the Python 3.13 supported runtime.
- Avoid vulnerability ignores that imply unsupported Python 3.7 package versions are fixed.
- Check related docs, `index.html`, and `uninstall.sh`.

## Target State

- `requirements.txt` represents the supported secure runtime dependency set.
- `requirements-legacy-py37.txt` represents the best-effort dependency set for Python runtimes older than 3.9.
- Python CI has a strict `python313-security` lane and a compatibility-only `python37-legacy-compat` lane.

## Phase Checklist

- [x] Phase 1: Split dependency manifests and CI lanes.
- [x] Phase 2: Update installer and docs to describe the dual-track policy.

## Work Log

### Phase 1

- Moved the main CI container to `python:3.13-trixie`.
- Added a `python37-legacy-compat` CI job using `python:3.7-buster`.
- Removed `pip-audit` from the legacy lane because several fixed dependency versions require Python newer than 3.7.

### Phase 2

- Updated `install.sh` to select the legacy requirements file by Python runtime version so Python 3.8 platforms use compatible packages.
- Updated development and manual install docs to explain which dependency set each lane uses.
- Updated `check_ci_docker.sh` so its default run covers both the Python 3.13 security lane and the Python 3.7 compatibility lane.
- Fixed the legacy syntax check to use Python 3.7's native parser without the newer `feature_version` argument.
- Renamed the workflow to `Python CI` in `.github/workflows/python-ci.yml`, with explicit lane names `python313-security` and `python37-legacy-compat`.

Docs/index/uninstall checks:

- `docs/development.md`, `docs/manual_install.md`, and `README.md` were checked or updated.
- `index.html` already links to the updated documentation files.
- `uninstall.sh` does not need changes because no installed files, services, timers, state directories, or system config were added.

Verification:

- `bash -n check_ci.sh`: passed.
- `bash -n check_ci_docker.sh`: passed.
- `bash -n install.sh`: passed.
- Workflow YAML parse via PyYAML: passed.
- `.venv/bin/python -m pip install --dry-run -r requirements.txt -r requirements-dev.txt`: passed with network access.
- `bash check_ci.sh`: passed with network access for pip-audit's temporary dependency resolution.
- Python 3.7 syntax parser check: passed.
- `bash check_ci_docker.sh`: Docker is installed in this workspace, but the daemon is not reachable, so container reproduction could not run here.

## Decisions

- Debian 13 / Python 3.13 is the strict security-supported baseline.
- Python runtimes older than 3.9 use the legacy dependency set, but dependency vulnerabilities that require newer Python are not ignored in audit output.

## Follow-Up Backlog

- Consider dropping Python 3.7 compatibility once Debian 10 legacy support is no longer needed.
