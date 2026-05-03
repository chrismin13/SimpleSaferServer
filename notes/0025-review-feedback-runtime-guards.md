# Review Feedback Runtime Guards

Follow-up review feedback was verified against the current tree before patching. The comments still
applied to installer control flow, Livepatch status collection, user creation persistence, SMART JSON
error parsing, and setup wizard error reporting.

The installer keeps the rclone download and installer execution in one conditional so either failure
uses the same non-fatal warning path. The generated background-service refresh now treats
`system.setup_complete` as either a stored string or a JSON boolean.

Livepatch status now returns the normal unavailable payload shape when the command adapter raises
before producing a process result. User creation also removes the transient in-memory user if Samba
sync has succeeded but JSON persistence fails, so a retry does not see a phantom duplicate.

SMART JSON reads now tolerate an empty `smartctl.messages` list when no ATA SMART table is available.
The setup wizard reports user creation and system configuration failures separately so operators know
which setup step actually failed.
