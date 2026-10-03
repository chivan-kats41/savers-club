import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import Area, TimeStampedModel


def generate_referral_code():
    return secrets.token_hex(4).upper()


class Member(TimeStampedModel):
    """Member profile. Subscription status lives on subscriptions.Subscription
    (Phase 4) — this model holds identity/area/referral only, so we don't
    duplicate a status that a real payment-backed model already owns."""

    class AccountStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="member_profile")
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="members")

    account_status = models.CharField(max_length=20, choices=AccountStatus.choices, default=AccountStatus.ACTIVE)

    referral_code = models.CharField(max_length=16, unique=True, default=generate_referral_code)
    referred_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return str(self.user)


class ReferralReward(TimeStampedModel):
    """One row per referred member who has activated a subscription for
    the first time — created automatically (see subscriptions.services.
    confirm_payment) the moment that first payment succeeds, so a
    referral is only ever rewarded once it's a real paying member, not
    just a signup. `referred_member` is OneToOne: each referred member
    can only generate one reward, ever.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CREDITED = "credited", "Credited"

    referrer = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="referral_rewards_earned")
    referred_member = models.OneToOneField(Member, on_delete=models.CASCADE, related_name="referral_reward_generated")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    credited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.referrer_id == self.referred_member_id:
            raise ValidationError("A member cannot refer themselves.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.referrer} earned {self.amount} for referring {self.referred_member}"
