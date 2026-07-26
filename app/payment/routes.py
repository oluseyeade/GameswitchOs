"""
Re-export shim from pkg.app.payment.routes.
"""
from pkg.app.payment.routes import create_payment_blueprint

__all__ = ["create_payment_blueprint"]
