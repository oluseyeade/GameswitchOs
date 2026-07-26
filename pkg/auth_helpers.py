from functools import wraps

from flask import redirect, session, url_for

from pkg.models import User


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.filter_by(id=user_id, is_active=True).first()


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("user.login"))
        return view_func(*args, **kwargs)

    return wrapper


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("user.login"))
            if user.role not in roles:
                return redirect(url_for("user.available_games"))
            return view_func(*args, **kwargs)

        return wrapper

    return decorator


def user_can_manage_branch(user: User, branch: str) -> bool:
    if user.role == "superadmin":
        return True
    if user.role == "admin1" and branch == "branch1":
        return True
    if user.role == "admin2" and branch == "branch2":
        return True
    return False


def get_redirect_for_role(role: str) -> str:
    if role == "admin1":
        return url_for("admin.admin1")
    if role == "admin2":
        return url_for("admin.admin2")
    if role == "superadmin":
        return url_for("admin.superadmin")
    return url_for("user.available_games")
