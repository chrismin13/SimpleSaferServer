# Review Feedback Hardening

Verified current review findings before changing code. The Python 3.7 lane remains a
best-effort compatibility lane instead of a dependency-audit lane because fixed package releases
for several dependencies require newer Python versions.

Changes in this pass focus on avoiding stale persisted config, preserving injected adapters in
rollback paths, returning explicit HTTP errors for invalid payloads, and keeping fallback runtime
state honest instead of substituting unrelated data.
