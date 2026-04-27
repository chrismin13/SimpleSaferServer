"""Compatibility module for SMB manager helpers."""

import sys as _sys

from simple_safer_server.services import smb_manager as _smb_manager_module

# Keep root and package imports bound to the same module object.
_sys.modules[__name__] = _smb_manager_module
