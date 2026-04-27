"""Compatibility module for user management helpers."""

import sys as _sys

from simple_safer_server.services import user_manager as _user_manager_module

# Keep root and package imports bound to the same module object.
_sys.modules[__name__] = _user_manager_module
