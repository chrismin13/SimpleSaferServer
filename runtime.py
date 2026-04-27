"""Compatibility module for runtime helpers.

This keeps the historical top-level import path while runtime code lives under
simple_safer_server.services.runtime.
"""

import sys as _sys

from simple_safer_server.services import runtime as _runtime_module

# Replace this module object with the canonical runtime module so mutable module
# globals (such as _runtime and _fake_state) remain shared across import paths.
_sys.modules[__name__] = _runtime_module
