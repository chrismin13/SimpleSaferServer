# Review Feedback Runtime Hardening

## Context

This task verifies and addresses review feedback across CI permissions, backup-drive command
execution, migration error wrapping, cloud backup schedule persistence, update-state durability,
API response status codes, fake runtime isolation, and small route consistency issues.

## Sudo Policy

SimpleSaferServer's installed web service is expected to run as root, so adapter code should invoke
privileged system binaries directly by default. Operator-facing documentation can still show
`sudo` because a human shell often starts as a non-root user.

Keep any non-root developer workflow explicit, such as an adapter-level `use_sudo` option, rather
than implicitly adding `sudo` based on host state. This keeps subprocess argv predictable in tests
and avoids failures on minimal systems where `sudo` is not installed.
