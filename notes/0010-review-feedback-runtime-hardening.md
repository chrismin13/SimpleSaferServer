# Review Feedback Runtime Hardening

## Context

This task verifies and addresses review feedback across CI permissions, backup-drive command
execution, migration error wrapping, cloud backup schedule persistence, update-state durability,
API response status codes, fake runtime isolation, and small route consistency issues.

## Sudo Policy

SimpleSaferServer's installed web service is expected to run as root, so adapter code invokes
privileged system binaries directly. Operator-facing documentation can still show `sudo` because a
human shell often starts as a non-root user.

Do not implicitly add `sudo` based on host state. This keeps subprocess argv predictable in tests
and avoids failures on minimal systems where `sudo` is not installed. Process-detection code may
still recognize `sudo` because operators can run package-manager commands from a shell.
