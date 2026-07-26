"""
Root routes re-export shim pointing to pkg.routes.
"""
from pkg.routes import create_admin_blueprints, create_user_blueprints

__all__ = ["create_admin_blueprints", "create_user_blueprints"]
