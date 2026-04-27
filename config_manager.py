"""Compatibility module for ConfigManager.

This keeps the historical top-level import path while the implementation lives
under simple_safer_server.services.config_manager.
"""

import sys as _sys

from simple_safer_server.services import config_manager as _config_manager_module

# Swap in the canonical module object to keep monkeypatching and introspection
# behavior identical across root and package import paths.
_sys.modules[__name__] = _config_manager_module
