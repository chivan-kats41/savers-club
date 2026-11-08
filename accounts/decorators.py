from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Allow access if request.user is authenticated and holds one of
    `roles` as their current active role (or is a superuser). Redirects
    anonymous users to login; raises 403 for a logged-in user with the
    wrong role rather than silently 404ing (so they know to switch role
    or that they lack access, instead of thinking the page is gone).
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not request.user.has_role(*roles):
                raise PermissionDenied("Your account does not have access to this page.")
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_admin():
            raise PermissionDenied("Admin access required.")
        return view_func(request, *args, **kwargs)

    return wrapped
