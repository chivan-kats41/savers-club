from django.contrib.auth.backends import ModelBackend

from .models import LoginAttempt, User

LOCKOUT_THRESHOLD = 5
LOCKOUT_WINDOW_MINUTES = 15


def login_ip_failure_limit() -> int:
    """Failed logins from ONE network address (all accounts together) before it is paused. Generous on purpose: many
    users share one carrier-NAT address."""
    from core.services import get_setting_int

    return max(10, get_setting_int("security.login_ip_failure_limit", 40))


class PhoneOrEmailBackend(ModelBackend):
    """Authenticates against either `phone` or `email`. Locks out an
    identifier (not an IP — deliberately, since Uganda phone numbers are
    often shared behind carrier NAT) after LOCKOUT_THRESHOLD recent
    failures, regardless of whether it resolves to a real account, so we
    never leak account existence through timing/lockout differences.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get("identifier")
        if not identifier or not password:
            return None

        if LoginAttempt.recent_failures(identifier, LOCKOUT_WINDOW_MINUTES) >= LOCKOUT_THRESHOLD:
            return None

        try:
            user = User.objects.get_by_natural_key(identifier)
        except User.DoesNotExist:
            user = User.objects.filter(email__iexact=identifier).first()

        if user is None or not user.check_password(password) or not self.user_can_authenticate(user):
            return None

        return user
