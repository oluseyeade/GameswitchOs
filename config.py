"""
Root configuration re-export shim pointing to pkg.config.
"""
from pkg.config import Config

__all__ = ["Config"]
