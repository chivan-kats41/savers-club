"""Idempotent starter data a fresh production database needs before the site is usable:
offer categories (merchants must pick one) and promotion packages (merchants buy these to boost offers).

Safe to re-run: existing rows are never overwritten, so anything an admin has edited is left alone.
Edit prices/labels afterwards in Admin console > Settings. Areas, plans and system settings come from
migrations / seed_subscription_plans / seed_system_settings.
"""
from django.core.management.base import BaseCommand

from offers.models import OfferCategory
from promotions.models import PromotionPackage

CATEGORIES = [
    ("general", "General Shop", "🏪"), ("soap", "Soap", "🧼"), ("rice", "Rice", "🍚"), ("posho", "Posho", "🌽"),
    ("sugar", "Sugar", "🍬"), ("oil", "Cooking Oil", "🛢️"), ("vegetables", "Vegetables", "🥬"),
    ("fruits", "Fruits", "🍌"), ("pharmacy", "Pharmacy", "💊"), ("food", "Food / Lunch", "🍛"),
    ("school", "School Items", "📚"), ("gas", "Gas", "🔥"), ("charcoal", "Charcoal", "🪵"),
    ("phone", "Phone & Data", "📱"), ("other", "Other", "📦"),
]

# (code, label, price UGX, duration days, visibility boost). Starting prices: change them to suit your market.
PACKAGES = [
    ("boost-1d", "Boost: 1 day", 2000, 1, 20),
    ("boost-3d", "Boost: 3 days", 5000, 3, 20),
    ("boost-7d", "Boost: 7 days", 10000, 7, 30),
]


class Command(BaseCommand):
    help = "Create default offer categories and promotion packages (idempotent; never overwrites existing rows)."

    def handle(self, *args, **opts):
        made_c = sum(OfferCategory.objects.get_or_create(key=k, defaults={"label": l, "emoji": e})[1] for k, l, e in CATEGORIES)
        made_p = sum(
            PromotionPackage.objects.get_or_create(
                code=c, defaults={"label": l, "price": p, "duration_days": d, "visibility_boost": b})[1]
            for c, l, p, d, b in PACKAGES
        )
        self.stdout.write(self.style.SUCCESS(
            f"Offer categories: {made_c} created, {len(CATEGORIES) - made_c} already present. "
            f"Promotion packages: {made_p} created, {len(PACKAGES) - made_p} already present."))
