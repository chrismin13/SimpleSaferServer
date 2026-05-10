# System Updates Cleanup Confirmation

The System Updates app-update panel now keeps the dirty status row short and puts the detailed
cleanup explanation in the confirmation modal.

The app update status API includes a capped `dirty_files` list from `git status --porcelain`.
Each item has a path and a coarse kind (`changed` or `extra`). The confirmation modal renders that
list inside a collapsed details section so administrators can inspect what will be reset or removed
without turning the main status row into a long paragraph.

The shared confirmation dialog accepts an optional DOM body. Existing text-only confirmations still
use the same `data-confirm` path and restore the pre-line body formatting on every call.
