# 0003 PR CI Review Stabilization

## Summary

- Stabilize PR #43 by fixing failing CI and working through actionable review comments.
- Keep fixes behavior-preserving unless a concrete bug is verified.

## Rules / Constraints

- Preserve Python 3.7 compatibility for Debian 10.
- Preserve user-facing behavior unless a bug is clearly found and documented.
- Keep changes reviewable and avoid unrelated formatting churn.
- Check related docs, `index.html`, and `uninstall.sh`.
- Keep review-comment fixes focused; move durable guidance to canonical docs when needed.

## Target State

- The Quality workflow passes on the PR branch.
- CodeRabbit comments that identify real bugs or maintainability risks are fixed or recorded as follow-up debt.
- Python 3.7-only failures are reproducible through the compatibility syntax check and guarded by tests where practical.

## Phase Checklist

- [x] Phase 1: Fix CI blockers from the Python 3.7 Quality job.
- [x] Phase 2: Address low-risk actionable review comments in touched areas.
- [x] Phase 3: Re-run local quality gates and record advisory findings.
- [x] Phase 4: Update docs or follow-up debt if the fixes reveal durable workflow or architecture guidance.

## Work Log

### Phase 1

- GitHub Quality workflow failed on commit `816de98` with 9 pytest failures.
- Confirmed the highest-priority failures include Python 3.7 incompatibility in `Path.unlink(missing_ok=True)` and backup schedule parsing that rejects the default `HH:MM:SS` value.
- Replaced `Path.unlink(missing_ok=True)` with a Python 3.7-compatible existence check.
- Made backup schedule parsing accept `HH:MM` and `HH:MM:SS`.
- Pinned the runtime Socket.IO stack to the same versions used by install/manual docs so CI does not resolve a different Python 3.7-compatible combination.
- Reworked uninstall cleanup parsing through Python helpers for config, fstab, and Samba markers so Debian 10 shell/awk differences do not change cleanup behavior.

### Phase 2

- Moved rclone password obfuscation input to stdin instead of argv in the CLI proof-of-concept and cloud backup service.
- Broadened non-fatal subprocess error handling for `msmtp` and SMB service enablement to include missing executable errors.
- Added an explicit seek before writing apt periodic config through `tee`.
- Added explicit HTTP error statuses for several route exception paths and guarded JSON body parsing in cloud backup, alerts, SMB, and user routes.
- Clamped task log line counts to avoid invalid or unbounded query values.

Docs and uninstall impact:

- `uninstall.sh` was updated because several CI failures came from uninstall cleanup tests.
- Runtime dependency pins align `requirements.txt` with existing `install.sh` and `docs/manual_install.md` guidance.

Verification:

- Python 3.7 syntax compatibility check passed.
- `ruff format --check .` passed.
- `ruff check .` passed.
- `pytest` passed locally on Python 3.14 with 163 tests and one existing `datetime.utcnow()` deprecation warning.
- `pyright` passed with 0 errors and 0 warnings.
- Bandit passed with no issues.
- `pip-audit` passed with no known vulnerabilities.
- No `index.html` link changes were needed because this slice did not add or move user/operator docs.

## Decisions

- Use this note because PR stabilization has meaningful task memory: CI logs, review-thread decisions, compatibility findings, and follow-up debt.
- Fix CI blockers before broader review comments so the branch gets back to a known-good baseline.

## Follow-Up Backlog

- Review unresolved comments that are not directly needed for CI after the Quality workflow is green.
- Decide whether dashboard health placeholders should be replaced with real drive-health summaries in a separate dashboard slice.
- Review remaining API routes for consistent shared JSON helpers instead of per-route payload construction.
