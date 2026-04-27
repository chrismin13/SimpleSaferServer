"""Compatibility module for system updates manager helpers."""

import sys as _sys

from simple_safer_server.services import system_updates as _system_updates_module

# Keep root and package imports bound to the same module object.
_sys.modules[__name__] = _system_updates_module
