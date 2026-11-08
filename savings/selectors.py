from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from offers.models import Offer

from .models import SavingsRecord


def confirmed_savings_total(member) -> Decimal:
    total = SavingsRecord.objects.filter(member=member).aggregate(total=Sum("saving_amount"))["total"]
    return total or Decimal("0")


def confirmed_savings_this_month(member) -> Decimal:
    now = timezone.now()
    total = SavingsRecord.objects.filter(
        member=member, created_at__year=now.year, created_at__month=now.month
    ).aggregate(total=Sum("saving_amount"))["total"]
    return total or Decimal("0")


def monthly_savings_history(member, months: int = 6):
    """Last `months` calendar months of confirmed savings, oldest first.
    Computed from SavingsRecord on every call — not cached/stored."""
    now = timezone.now()
    buckets = []
    for i in range(months - 1, -1, -1):
        # Walk back i months from the first of this month.
        year = now.year
        month = now.month - i
        while month < 1:
            month += 12
            year -= 1
        total = SavingsRecord.objects.filter(
            member=member, created_at__year=year, created_at__month=month
        ).aggregate(total=Sum("saving_amount"))["total"] or Decimal("0")
        buckets.append({"year": year, "month": month, "saved": total})
    return buckets


def possible_savings_total(member) -> Decimal:
    """Sum of (normal_price - member_price) across currently active,
    unexpired offers in the member's area — what they *could* still
    save, distinct from what they've confirmed via SavingsRecord."""
    offers = Offer.objects.filter(area=member.area, status=Offer.Status.ACTIVE, expires_at__gt=timezone.now())
    total = Decimal("0")
    for offer in offers:
        total += offer.possible_saving
    return total


def savings_summary(member) -> dict:
    return {
        "confirmed_total": confirmed_savings_total(member),
        "confirmed_this_month": confirmed_savings_this_month(member),
        "possible_total": possible_savings_total(member),
        "claims_count": member.claims.filter(status="redeemed").count(),
    }
