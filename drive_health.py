"""Compatibility module for drive health helpers."""

import sys as _sys

from simple_safer_server.services import drive_health as _drive_health_module

# Keep root and package imports bound to the same module object.
_sys.modules[__name__] = _drive_health_module
