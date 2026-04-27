"""Compatibility module for system utility helpers."""

import sys as _sys

from simple_safer_server.services import system_utils as _system_utils_module

# Keep root and package imports bound to the same module object.
_sys.modules[__name__] = _system_utils_module
