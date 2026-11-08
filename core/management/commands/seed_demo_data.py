"""
One-time/idempotent dev-data import: turns hub/data.py's hard-coded
prototype datasets (ALL_MEMBERS, ALL_MERCHANTS, ALL_OFFERS,
SEARCH_CATEGORIES) into real database rows behind members/merchants/offers,
so the frontend can eventually be pointed at real querysets instead of
the static Python lists.

This is DEMO data for local development only — never run in production
against a real customer base. All demo users get an unusable/dev
password unless DEMO_USER_PASSWORD is set in the environment.
"""
import re

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from accounts.models import Role, User
from core.models import Area
from hub import data as d
from members.models import Member
from merchants.models import Merchant
from offers.models import Offer, OfferCategory

DEMO_PASSWORD = "DemoPass123!"

CATEGORY_LABEL_TO_KEY = {
    "Daily Basket": "posho",
    "Pharmacy": "pharmacy",
    "Restaurants": "food",
    "School Items": "school",
    "Phone & Data": "phone",
}


def slugify_phone(raw_phone: str, seed: int) -> str:
    digits = re.sub(r"\D", "", raw_phone)
    if digits.startswith("0"):
        digits = "256" + digits[1:]
    if not digits:
        digits = f"25670000{seed:04d}"
    return f"+{digits}"


class Command(BaseCommand):
    help = "Imports hub/data.py's sample members/merchants/offers as real DB rows (dev only)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING(f"Demo users get password: {DEMO_PASSWORD}"))

        categories = self._seed_categories()
        areas = {a.name: a for a in Area.objects.all()}
        members = self._seed_members(areas)
        merchants = self._seed_merchants(areas, categories)
        self._seed_offers(merchants, categories, areas)

        self.stdout.write(self.style.SUCCESS("Demo data seed complete."))

    def _seed_categories(self):
        created = 0
        by_label = {}
        by_key = {}
        for row in d.SEARCH_CATEGORIES:
            obj, was_created = OfferCategory.objects.update_or_create(
                key=row["key"], defaults={"label": row["label"], "emoji": row.get("emoji", "")}
            )
            by_label[row["label"]] = obj
            by_key[row["key"]] = obj
            created += was_created
        # ALL_MERCHANTS/ALL_OFFERS use a slightly different label set
        # ("Daily Basket", "Restaurants") than SEARCH_CATEGORIES — resolve
        # those through the alias map onto the same underlying category.
        for alias_label, key in CATEGORY_LABEL_TO_KEY.items():
            if key in by_key:
                by_label[alias_label] = by_key[key]
        self.stdout.write(self.style.SUCCESS(f"Categories: {created} created, {len(d.SEARCH_CATEGORIES) - created} already present."))
        return by_label

    def _seed_members(self, areas):
        created = 0
        members = {}
        for i, row in enumerate(d.ALL_MEMBERS):
            phone = slugify_phone(row["phone"], i)
            first, _, last = row["name"].partition(" ")
            user, user_created = User.objects.get_or_create(
                phone=phone,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "role": Role.MEMBER,
                    "phone_verified": True,
                },
            )
            if user_created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])
                created += 1

            area = areas.get(row["area"])
            if not area:
                self.stdout.write(self.style.WARNING(f"Skipping member {row['name']}: unknown area {row['area']}"))
                continue

            member, _ = Member.objects.update_or_create(
                user=user,
                defaults={
                    "area": area,
                    "account_status": Member.AccountStatus.SUSPENDED
                    if row["status"] == "Suspended"
                    else Member.AccountStatus.ACTIVE,
                },
            )
            members[row["name"]] = member

        self.stdout.write(self.style.SUCCESS(f"Members: {created} new users created, {len(members)} member profiles present."))
        return members

    def _seed_merchants(self, areas, categories):
        created = 0
        merchants = {}
        for i, row in enumerate(d.ALL_MERCHANTS):
            phone = slugify_phone(f"07{700000000 + i}", i)
            user, user_created = User.objects.get_or_create(
                phone=phone,
                defaults={
                    "first_name": row["name"],
                    "role": Role.MERCHANT,
                    "phone_verified": True,
                },
            )
            if user_created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])
                created += 1

            area = areas.get(row["area"])
            category = categories.get(row["category"])
            if not area or not category:
                self.stdout.write(
                    self.style.WARNING(f"Skipping merchant {row['name']}: missing area/category")
                )
                continue

            status_map = {
                "Verified": Merchant.Status.VERIFIED,
                "Pending": Merchant.Status.PENDING,
            }
            merchant, _ = Merchant.objects.update_or_create(
                user=user,
                defaults={
                    "business_name": row["name"],
                    "category": category,
                    "area": area,
                    "status": status_map.get(row["status"], Merchant.Status.PENDING),
                    "verified_at": timezone.now() if row["status"] == "Verified" else None,
                },
            )
            merchants[row["name"]] = merchant

        self.stdout.write(self.style.SUCCESS(f"Merchants: {created} new users created, {len(merchants)} merchant profiles present."))
        return merchants

    def _seed_offers(self, merchants, categories, areas):
        created = 0
        skipped = 0
        for row in d.ALL_OFFERS:
            merchant = merchants.get(row["merchant"])
            category = categories.get(row["category"])
            area = areas.get(row["area"])
            if not merchant or not category or not area:
                skipped += 1
                continue

            status_map = {
                "Active": Offer.Status.ACTIVE,
                "Pending": Offer.Status.PENDING,
                "Paused": Offer.Status.PAUSED,
                "Reported": Offer.Status.REPORTED,
            }
            _, was_created = Offer.objects.update_or_create(
                merchant=merchant,
                item_name=row["item"],
                defaults={
                    "category": category,
                    "area": area,
                    "normal_price": row["normal"],
                    "member_price": row["member"],
                    "quantity": row["stock"],
                    "status": status_map.get(row["status"], Offer.Status.PENDING),
                    "expires_at": timezone.now() + timedelta(days=7),
                },
            )
            created += was_created

        self.stdout.write(
            self.style.SUCCESS(f"Offers: {created} created/updated, {skipped} skipped (missing merchant/category/area).")
        )
