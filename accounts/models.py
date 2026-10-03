import hashlib
import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class Role(models.TextChoices):
    MEMBER = "member", "Member"
    MERCHANT = "merchant", "Merchant"
    RIDER = "rider", "Rider"
    AGENT = "agent", "Agent"
    ADMIN = "admin", "Admin"
    SUPER_ADMIN = "super_admin", "Super Admin"


ADMIN_ROLES = {Role.ADMIN, Role.SUPER_ADMIN}


class User(AbstractBaseUser, PermissionsMixin):
    """Identity + primary role only for now. Multi-role assignment
    (a user who is both a Member and a Rider, with role-switching),
    phone/email verification records, login-attempt tracking, and
    granular permissions are added in Phase 2 — this model exists in
    Phase 1 purely so AUTH_USER_MODEL can be set before the first
    migration, as Django requires.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    phone = models.CharField(max_length=20, unique=True)
    email = models.EmailField(unique=True, null=True, blank=True)

    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)

    phone_verified = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # TOTP two-factor (required for admin accounts in production, see core/twofa.py)
    totp_secret = models.CharField(max_length=64, blank=True, editable=False)
    totp_enabled = models.BooleanField(default=False)

    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email or self.phone

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.phone

    def get_short_name(self):
        return self.first_name or self.phone

    def role_names(self):
        """All roles this user is allowed to switch into (active UserRole
        rows), including their current primary `role` for safety."""
        assigned = set(self.assigned_roles.filter(is_active=True).values_list("role", flat=True))
        assigned.add(self.role)
        return assigned

    def has_role(self, *roles):
        if self.is_superuser:
            return True
        return bool(self.role_names() & set(roles))

    def is_admin(self):
        return self.is_superuser or self.role in ADMIN_ROLES


class UserRole(models.Model):
    """A role a user is permitted to switch into. `User.role` is the
    currently *active* role (drives dashboard/permission checks);
    UserRole is the set of roles they're allowed to switch between —
    e.g. someone can be both a Member and a Rider.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="assigned_roles")
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "role")

    def __str__(self):
        return f"{self.user} -> {self.role}"


def _hash_code(raw_code: str) -> str:
    return hashlib.sha256(raw_code.encode()).hexdigest()


class PhoneVerification(models.Model):
    """Hashed OTP for phone verification / phone-based login / password
    reset. The raw code is never stored — only its SHA-256 hash."""

    class Purpose(models.TextChoices):
        REGISTRATION = "registration", "Registration"
        LOGIN = "login", "Login"
        PASSWORD_RESET = "password_reset", "Password reset"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="phone_verifications")
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "purpose", "is_used"])]

    @classmethod
    def issue(cls, user, purpose, ttl_minutes=10):
        raw_code = f"{secrets.randbelow(10_000):04d}"
        obj = cls.objects.create(
            user=user,
            purpose=purpose,
            code_hash=_hash_code(raw_code),
            expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
        )
        return obj, raw_code

    def is_valid(self):
        return not self.is_used and self.attempts < self.max_attempts and timezone.now() < self.expires_at

    def verify_code(self, raw_code):
        """Verify + consume one attempt. Returns True only on a correct,
        still-valid code; marks itself used on success."""
        if not self.is_valid():
            return False
        self.attempts += 1
        matched = secrets.compare_digest(self.code_hash, _hash_code(raw_code))
        if matched:
            self.is_used = True
        self.save(update_fields=["attempts", "is_used"])
        return matched


class EmailVerification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_verifications")
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def issue(cls, user, ttl_hours=48):
        return cls.objects.create(user=user, expires_at=timezone.now() + timedelta(hours=ttl_hours))

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at


class LoginAttempt(models.Model):
    """Every login attempt, success or failure, keyed by the identifier
    typed in (phone or email) — used for lockout/rate-limit decisions
    independent of whether that identifier resolves to a real user."""

    identifier = models.CharField(max_length=150, db_index=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="login_attempts")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    success = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["identifier", "created_at"])]

    @classmethod
    def recent_failures(cls, identifier, minutes=15):
        since = timezone.now() - timedelta(minutes=minutes)
        return cls.objects.filter(identifier=identifier, success=False, created_at__gte=since).count()


class SecurityEvent(models.Model):
    """Account-security-relevant events: password change, phone/email
    change, role switch, lockout triggered, etc. Distinct from core.AuditLog
    (which is the general-purpose, cross-domain audit trail) so security
    tooling can query just this table cheaply."""

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="security_events")
    event_type = models.CharField(max_length=50)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "event_type", "created_at"])]

    def __str__(self):
        return f"{self.event_type} - {self.user} @ {self.created_at:%Y-%m-%d %H:%M}"
