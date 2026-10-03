"""Require TOTP two-factor for every admin surface.

One middleware covers the admin console, Django admin and the admin API, so
no individual view can forget the check. Controlled by ADMIN_REQUIRE_2FA
(on in production, off in development/testing).
"""
import time

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

SESSION_KEY = "admin_2fa_user"
SESSION_TS = "admin_2fa_at"
PROTECTED_PREFIXES = ("/admin-console/", "/django-admin/", "/api/v1/admin/")
EXEMPT_PREFIXES = ("/accounts/2fa/", "/accounts/logout/", "/static/")


def is_verified(request) -> bool:
    user = request.user
    if request.session.get(SESSION_KEY) != str(user.pk):
        return False
    max_age = getattr(settings, "ADMIN_2FA_MAX_AGE_SECONDS", 12 * 3600)
    return (time.time() - request.session.get(SESSION_TS, 0)) < max_age


def mark_verified(request):
    request.session[SESSION_KEY] = str(request.user.pk)
    request.session[SESSION_TS] = time.time()


class AdminTwoFactorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "ADMIN_REQUIRE_2FA", False):
            path = request.path
            user = getattr(request, "user", None)
            if (
                path.startswith(PROTECTED_PREFIXES)
                and not path.startswith(EXEMPT_PREFIXES)
                and user is not None
                and user.is_authenticated
                and user.is_admin()
                and not is_verified(request)
            ):
                if path.startswith("/api/"):
                    return JsonResponse(
                        {"success": False, "error": {"code": "TWO_FACTOR_REQUIRED",
                                                     "message": "Two-factor verification required.", "details": {}}},
                        status=403,
                    )
                name = "accounts:2fa_verify" if user.totp_enabled else "accounts:2fa_setup"
                return redirect(f"{reverse(name)}?next={request.get_full_path()}")
        return self.get_response(request)
