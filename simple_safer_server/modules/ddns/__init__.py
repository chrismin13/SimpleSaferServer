"""DDNS module package."""

from simple_safer_server.modules.ddns.module import create_module
from simple_safer_server.modules.ddns.service import DdnsService

__all__ = ["DdnsService", "create_module"]
