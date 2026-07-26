"""
Re-export shim from pkg.app.payment.
"""
from pkg.app.payment import create_payment_blueprint

__all__ = ["create_payment_blueprint"]
