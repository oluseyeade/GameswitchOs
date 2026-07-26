"""
Root extensions re-export shim pointing to pkg.extensions.
"""
from pkg.extensions import db, migrate

__all__ = ["db", "migrate"]
