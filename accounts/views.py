import logging

from django.conf import settings
from django.views.decorators.http import require_POST
from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

from core.middleware import get_client_ip
from core.rate_limit import rate_limit
from core.services import record_risk_event
from notifications.services.dispatch import notify
from .authentication import LOCKOUT_THRESHOLD, LOCKOUT_WINDOW_MINUTES
from .forms import (
    LoginForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
    PhoneVerifyForm,
    RegisterForm,
)
from .models import LoginAttempt, PhoneVerification, Role, SecurityEvent, User, UserRole

security_logger = logging.getLogger("security")

ROLE_DASHBOARD_URL = {
    Role.MEMBER: "member",
    Role.MERCHANT: "merchant",
    Role.RIDER: "rider",
    Role.AGENT: "agent",
    Role.ADMIN: "admin_index",
    Role.SUPER_ADMIN: "admin_index",
}


def _dashboard_redirect(user):
    return redirect(ROLE_DASHBOARD_URL.get(user.role, "landing"))


OTP_MESSAGES = {
    "registration": "verify your phone number",
    "password-reset": "reset your password",
}


def _send_otp_dev(user, otp, purpose):
    """Deliver a one-time code to the user's phone by SMS (ioTec Messaging in
    production; logged to the console in development).

    The code is never logged by the server. It is only handed back to the view
    when DEBUG is on, so the flow can be exercised locally without a provider;
    outside DEBUG it is delivered by SMS only.
    """
    from notifications.services.sms_gateway import send_sms

    reason = OTP_MESSAGES.get(purpose.split("-resend")[0], "continue")
    text = f"1K Saver Club: {otp} is your code to {reason}. It expires in 10 minutes. Never share it with anyone."
    sent = send_sms(user.phone, text)
    security_logger.info("OTP issued user=%s purpose=%s sms_accepted=%s", user.id, purpose, sent)
    if not sent:
        security_logger.warning("OTP SMS could not be sent user=%s purpose=%s (user can request a new code)", user.id, purpose)
    return otp if settings.DEBUG else None


@rate_limit("register", limit=10, period_seconds=3600)
def register(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            user = User.objects.create_user(
                phone=data["phone"],
                email=data["email"],
                password=data["password"],
                first_name=data["first_name"],
                last_name=data["last_name"],
                role=Role.MEMBER,
            )
            UserRole.objects.create(user=user, role=Role.MEMBER)

            from members.models import Member

            referred_by = None
            referral_code = data.get("referral_code", "").strip().upper()
            if referral_code:
                referred_by = Member.objects.filter(referral_code=referral_code).first()
            Member.objects.create(user=user, area=data["area"], referred_by=referred_by)

            verification, raw_code = PhoneVerification.issue(user, PhoneVerification.Purpose.REGISTRATION)
            dev_code = _send_otp_dev(user, raw_code, "registration")
            request.session["pending_verify_user_id"] = str(user.id)
            SecurityEvent.objects.create(
                user=user, event_type="registration", ip_address=get_client_ip(request)
            )
            notify(
                user, "registration", "Welcome to 1K Saver Club",
                "Your account has been created. Verify your phone to get started.",
            )
            if dev_code:
                messages.info(request, f"[DEV ONLY] Your verification code is {dev_code}")
            return redirect("accounts:verify_phone")
        return render(request, "accounts/register.html", {"form": form})
    return render(request, "accounts/register.html", {"form": RegisterForm(initial={"referral_code": request.GET.get("ref", "")})})


def verify_phone(request):
    user_id = request.session.get("pending_verify_user_id")
    if not user_id:
        return redirect("accounts:login")
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect("accounts:login")

    if request.method == "POST":
        form = PhoneVerifyForm(request.POST)
        if form.is_valid():
            verification = (
                PhoneVerification.objects.filter(user=user, is_used=False)
                .order_by("-created_at")
                .first()
            )
            if verification and verification.verify_code(form.cleaned_data["code"]):
                user.phone_verified = True
                user.save(update_fields=["phone_verified"])
                SecurityEvent.objects.create(
                    user=user, event_type="phone_verified", ip_address=get_client_ip(request)
                )
                del request.session["pending_verify_user_id"]
                django_login(request, user, backend="accounts.authentication.PhoneOrEmailBackend")
                messages.success(request, "Phone verified.")
                return _dashboard_redirect(user)
            form.add_error("code", "Invalid or expired code.")
        return render(request, "accounts/verify_phone.html", {"form": form})
    return render(request, "accounts/verify_phone.html", {"form": PhoneVerifyForm()})


@rate_limit("resend_otp", limit=5, period_seconds=3600)
def resend_phone_otp(request):
    user_id = request.session.get("pending_verify_user_id")
    if not user_id:
        return redirect("accounts:login")
    user = User.objects.filter(id=user_id).first()
    if user:
        verification, raw_code = PhoneVerification.issue(user, PhoneVerification.Purpose.REGISTRATION)
        dev_code = _send_otp_dev(user, raw_code, "registration-resend")
        if dev_code:
            messages.info(request, f"[DEV ONLY] Your new verification code is {dev_code}")
    return redirect("accounts:verify_phone")


def login_view(request):
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            identifier = form.cleaned_data["identifier"]
            password = form.cleaned_data["password"]
            ip = get_client_ip(request)

            if LoginAttempt.recent_failures(identifier, LOCKOUT_WINDOW_MINUTES) >= LOCKOUT_THRESHOLD:
                form.add_error(None, "Too many failed attempts. Try again later.")
                security_logger.warning("Lockout hit for identifier=%s ip=%s", identifier, ip)
                record_risk_event("login_lockout", ip_address=ip, metadata={"identifier": identifier})
                return render(request, "accounts/login.html", {"form": form})

            user = authenticate(request, username=identifier, password=password)
            LoginAttempt.objects.create(
                identifier=identifier, user=user, ip_address=ip, success=bool(user)
            )
            if user is None:
                form.add_error(None, "Invalid credentials.")
                return render(request, "accounts/login.html", {"form": form})

            django_login(request, user)
            request.session.cycle_key()
            SecurityEvent.objects.create(user=user, event_type="login", ip_address=ip)
            return _dashboard_redirect(user)
        return render(request, "accounts/login.html", {"form": form})
    return render(request, "accounts/login.html", {"form": LoginForm()})


@require_POST
@login_required
def logout_view(request):
    SecurityEvent.objects.create(
        user=request.user, event_type="logout", ip_address=get_client_ip(request)
    )
    django_logout(request)
    return redirect("landing")


@rate_limit("password_reset_request", limit=5, period_seconds=3600)
def password_reset_request(request):
    if request.method == "POST":
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            identifier = form.cleaned_data["identifier"]
            user = User.objects.filter(phone=identifier).first() or User.objects.filter(
                email__iexact=identifier
            ).first()
            # Always behave the same whether or not the account exists,
            # to avoid leaking account existence.
            if user:
                verification, raw_code = PhoneVerification.issue(
                    user, PhoneVerification.Purpose.PASSWORD_RESET
                )
                dev_code = _send_otp_dev(user, raw_code, "password-reset")
                request.session["pending_reset_user_id"] = str(user.id)
                if dev_code:
                    messages.info(request, f"[DEV ONLY] Your reset code is {dev_code}")
            messages.info(request, "If that account exists, a reset code has been sent.")
            return redirect("accounts:password_reset_confirm")
        return render(request, "accounts/password_reset_request.html", {"form": form})
    return render(request, "accounts/password_reset_request.html", {"form": PasswordResetRequestForm()})


def password_reset_confirm(request):
    user_id = request.session.get("pending_reset_user_id")
    if request.method == "POST":
        form = PasswordResetConfirmForm(request.POST)
        if form.is_valid() and user_id:
            user = User.objects.filter(id=user_id).first()
            verification = (
                PhoneVerification.objects.filter(
                    user=user, purpose=PhoneVerification.Purpose.PASSWORD_RESET, is_used=False
                )
                .order_by("-created_at")
                .first()
                if user
                else None
            )
            if user and verification and verification.verify_code(form.cleaned_data["code"]):
                user.set_password(form.cleaned_data["new_password"])
                user.save(update_fields=["password"])
                SecurityEvent.objects.create(
                    user=user, event_type="password_reset", ip_address=get_client_ip(request)
                )
                del request.session["pending_reset_user_id"]
                messages.success(request, "Password reset. You can log in now.")
                return redirect("accounts:login")
            form.add_error("code", "Invalid or expired code.")
        return render(request, "accounts/password_reset_confirm.html", {"form": form})
    return render(
        request, "accounts/password_reset_confirm.html", {"form": PasswordResetConfirmForm()}
    )


@login_required
def switch_role(request):
    if request.method != "POST":
        return redirect(request.META.get("HTTP_REFERER", reverse("landing")))
    target_role = request.POST.get("role")
    allowed = UserRole.objects.filter(user=request.user, role=target_role, is_active=True).exists()
    if not allowed:
        messages.error(request, "You are not assigned that role.")
        return redirect(request.META.get("HTTP_REFERER", reverse("landing")))
    request.user.role = target_role
    request.user.save(update_fields=["role"])
    SecurityEvent.objects.create(
        user=request.user,
        event_type="role_switch",
        ip_address=get_client_ip(request),
        metadata={"role": target_role},
    )
    return _dashboard_redirect(request.user)


# ---------------------------------------------------------------------------
# Admin: user suspension (capability-gated, never is_staff-only — see spec
# section 28). Implemented as DRF APIViews below rather than function views
# to sit alongside the rest of the admin API surface at /api/v1/admin/.
# ---------------------------------------------------------------------------
from rest_framework.permissions import IsAuthenticated  # noqa: E402
from rest_framework.response import Response  # noqa: E402
from rest_framework.views import APIView  # noqa: E402

from core.models import AuditLog  # noqa: E402
from core.middleware import get_client_ip as _get_client_ip  # noqa: E402
from .permissions import HasCapability  # noqa: E402

CanSuspendUsers = HasCapability.for_capability("users_suspend")


class SuspendUserView(APIView):
    permission_classes = [IsAuthenticated, CanSuspendUsers]

    def post(self, request, user_id):
        target = User.objects.filter(pk=user_id).first()
        if target is None:
            return Response(
                {"success": False, "error": {"code": "NOT_FOUND", "message": "User not found.", "details": {}}},
                status=404,
            )
        if target.is_superuser and not request.user.is_superuser:
            return Response(
                {"success": False, "error": {"code": "FORBIDDEN", "message": "Only a super admin can suspend another super admin.", "details": {}}},
                status=403,
            )
        target.is_active = False
        target.save(update_fields=["is_active"])
        AuditLog.objects.create(
            actor=request.user, action="user_suspended", object_type="User", object_id=str(target.id),
            ip_address=_get_client_ip(request),
        )
        return Response({"success": True, "data": {"id": str(target.id), "is_active": target.is_active}})


class ReactivateUserView(APIView):
    permission_classes = [IsAuthenticated, CanSuspendUsers]

    def post(self, request, user_id):
        target = User.objects.filter(pk=user_id).first()
        if target is None:
            return Response(
                {"success": False, "error": {"code": "NOT_FOUND", "message": "User not found.", "details": {}}},
                status=404,
            )
        target.is_active = True
        target.save(update_fields=["is_active"])
        AuditLog.objects.create(
            actor=request.user, action="user_reactivated", object_type="User", object_id=str(target.id),
            ip_address=_get_client_ip(request),
        )
        return Response({"success": True, "data": {"id": str(target.id), "is_active": target.is_active}})


# ---------------------------------------------------------------------------
# Two-factor (TOTP) for admin accounts
# ---------------------------------------------------------------------------
from django.utils.http import url_has_allowed_host_and_scheme  # noqa: E402

from . import totp  # noqa: E402
from core import twofa  # noqa: E402


def _safe_next(request, default="admin_index"):
    nxt = request.GET.get("next") or request.POST.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return nxt
    return reverse(default)


@login_required
def twofa_setup(request):
    user = request.user
    if not user.is_admin():
        return redirect("landing")
    if user.totp_enabled:
        return redirect("accounts:2fa_verify")
    secret = request.session.get("pending_totp_secret") or totp.new_secret()
    request.session["pending_totp_secret"] = secret
    error = ""
    if request.method == "POST":
        if rate_limit_hit(request, "2fa_setup"):
            error = "Too many attempts. Wait a few minutes."
        elif totp.verify(secret, request.POST.get("code", "")):
            user.totp_secret = secret
            user.totp_enabled = True
            user.save(update_fields=["totp_secret", "totp_enabled"])
            request.session.pop("pending_totp_secret", None)
            twofa.mark_verified(request)
            SecurityEvent.objects.create(user=user, event_type="2fa_enabled", ip_address=get_client_ip(request))
            return redirect(_safe_next(request))
        else:
            error = "That code didn't match. Check the time on your phone and try again."
    return render(request, "accounts/2fa_setup.html", {
        "secret": secret, "uri": totp.provisioning_uri(secret, user.phone), "error": error,
        "next": request.GET.get("next", ""),
    })


@login_required
def twofa_verify(request):
    user = request.user
    if not user.is_admin():
        return redirect("landing")
    if not user.totp_enabled:
        return redirect("accounts:2fa_setup")
    error = ""
    if request.method == "POST":
        if rate_limit_hit(request, "2fa_verify"):
            error = "Too many attempts. Wait a few minutes."
        elif totp.verify(user.totp_secret, request.POST.get("code", "")):
            twofa.mark_verified(request)
            SecurityEvent.objects.create(user=user, event_type="2fa_verified", ip_address=get_client_ip(request))
            return redirect(_safe_next(request))
        else:
            SecurityEvent.objects.create(user=user, event_type="2fa_failed", ip_address=get_client_ip(request))
            error = "Invalid code."
    return render(request, "accounts/2fa_verify.html", {"error": error, "next": request.GET.get("next", "")})


def rate_limit_hit(request, scope, limit=8, window=600) -> bool:
    """Tiny cache-based limiter: True once `limit` POSTs/`window` seconds from this user+IP."""
    from django.core.cache import cache

    key = f"rl:{scope}:{request.user.pk}:{get_client_ip(request)}"
    n = cache.get(key, 0) + 1
    cache.set(key, n, window)
    return n > limit
