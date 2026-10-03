from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import Area, SystemSetting
from hub.data import AREAS, LAUNCH_AREAS


class Command(BaseCommand):
    help = (
        "One-time/idempotent seed: imports hub/data.py's AREAS + "
        "LAUNCH_AREAS into core.Area, and writes the default business "
        "settings (subscription price, commission %, OTP/claim expiry) "
        "into core.SystemSetting so admins can edit them without a "
        "code deploy. Safe to re-run — uses update_or_create throughout."
    )

    def handle(self, *args, **options):
        launch_set = set(LAUNCH_AREAS)
        created, updated = 0, 0
        for name in AREAS:
            _, was_created = Area.objects.update_or_create(
                name=name,
                defaults={"is_launch_area": name in launch_set, "is_active": True},
            )
            created += was_created
            updated += not was_created

        self.stdout.write(self.style.SUCCESS(f"Areas: {created} created, {updated} already present."))

        defaults = {
            "subscription.price_ugx": (
                str(settings.DEFAULT_SUBSCRIPTION_PRICE_UGX),
                "1K Saver Club monthly subscription price (UGX).",
            ),
            "delivery.route_commission_percent": (
                str(settings.DEFAULT_ROUTE_COMMISSION_PERCENT),
                "Platform commission on shared-route delivery earnings (%).",
            ),
            "delivery.fare_same_area": ("2000", "Delivery fare (UGX) when seller and buyer are in the same area."),
            "delivery.fare_cross_area": ("4000", "Delivery fare (UGX) between different areas."),
            "delivery.fare_shared_route": ("2000", "Delivery fare (UGX) for shared-route delivery."),
            "claim.code_expiry_hours": (
                str(settings.CLAIM_CODE_EXPIRY_HOURS),
                "Hours before an unredeemed claim code expires.",
            ),
            "delivery.otp_expiry_minutes": (
                str(settings.DELIVERY_OTP_EXPIRY_MINUTES),
                "Minutes before a delivery OTP expires.",
            ),
            "delivery.otp_max_attempts": (
                str(settings.DELIVERY_OTP_MAX_ATTEMPTS),
                "Max wrong-OTP attempts before lockout.",
            ),
            "payment.reconciliation_timeout_minutes": (
                "60",
                "Minutes a payment can stay PENDING before reconciliation flags it REQUIRES_REVIEW.",
            ),
            "withdrawal.minimum_ugx": (
                "2000",
                "Minimum amount a rider/merchant/agent can withdraw in one request (UGX).",
            ),
            "withdrawal.fee_percent": (
                "1.00",
                "Platform fee charged on withdrawals (%).",
            ),
            "agent.merchant_verification_fee_ugx": (
                "500",
                "Flat fee credited to an agent for each merchant they verify (UGX).",
            ),
            "agent.rider_verification_fee_ugx": (
                "500",
                "Flat fee credited to an agent for each rider they verify (UGX).",
            ),
            "referral.reward_ugx": (
                "500",
                "Reward credited to a member when someone they referred activates their first subscription (UGX).",
            ),
        }

        setting_created = 0
        for key, (value, description) in defaults.items():
            _, was_created = SystemSetting.objects.get_or_create(
                key=key, defaults={"value": value, "description": description}
            )
            setting_created += was_created

        self.stdout.write(
            self.style.SUCCESS(
                f"SystemSettings: {setting_created} created "
                f"({len(defaults) - setting_created} already present, left untouched)."
            )
        )
