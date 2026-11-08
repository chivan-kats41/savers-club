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
            "withdrawal.require_code": (
                "1", "1 = every withdrawal needs a one-time code texted to the account's phone. Set 0 only for local testing without SMS.",
            ),
            "withdrawal.daily_limit_ugx": (
                "1000000", "Most (UGX) one person can withdraw in any rolling 24 hours. Limits the damage if an account is taken over.",
            ),
            "security.login_ip_failure_limit": (
                "40", "Failed logins from ONE network address (all accounts together) in 15 minutes before that address is paused. Keep generous: many users share one carrier address.",
            ),
            "geo.nearby_radius_km": (
                "6", "How far (km) a deal can be from a member and still count as \"near you\" on the landing page and alerts.",
            ),
            "geo.fresh_minutes": (
                "120", "How long (minutes) a member's last shared location is trusted before falling back to their area.",
            ),
            "geo.history_retention_days": (
                "30", "Days a member's location history is kept before it is automatically deleted.",
            ),
            "geo.rider_live_retention_days": (
                "7", "Days a rider's live delivery positions are kept before they are automatically deleted.",
            ),
            "geo.dropoff_max_km_from_area": (
                "15", "A delivery drop-off pin farther than this (km) from the chosen area's centre is refused.",
            ),
            "geo.merchant_max_km_from_area": (
                "15", "A shop pin farther than this (km) from the merchant's area centre is refused.",
            ),
            "geo.boda_speed_kmh": (
                "22", "Average boda speed (km/h) used for ETA estimates when the road router is unavailable.",
            ),
            "referral.hold_days": (
                "7",
                "Days a referral reward is held after the friend's first payment before it becomes withdrawable.",
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
