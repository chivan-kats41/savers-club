"""Database-backed read models for the hub templates.

Every function here returns plain dicts/lists shaped for the templates
(the same field names the old ``hub/data.py`` mock lists used, wherever a
real equivalent exists) so the views stay thin and the templates stay
declarative. Nothing in this module writes to the database.

Design rules
------------
* Per-user pages (member / merchant / rider / agent) are always scoped from
  ``request.user`` — no ID from the URL or query string ever decides whose
  data is shown.
* Where the schema has no model for something the old prototype showed
  (merchant reviews, pickup points, campaigns, agent tasks ...), we return
  ``None`` / an empty list rather than inventing numbers. Templates render an
  honest empty state for those.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Case, Count, DecimalField, F, IntegerField, Max, Min, Q, Sum, Value, When
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from accounts.models import User
from agents.models import Agent, AgentEarning, AgentTask, PriceRecord
from claims.models import ClaimEvent, OfferClaim
from complaints.models import Complaint
from core.models import Area, RiskEvent
from deliveries.models import DeliveryJob, PickupPoint, RiderEarning, SharedRoute
from item_requests.models import MemberRequest
from members.models import Member, ReferralReward
from merchants.models import Merchant
from notifications.models import Notification
from offers.models import Offer, OfferCategory, OfferInteraction
from payments.models import Payment, Withdrawal
from promotions.models import PromotionPackage
from riders.models import Rider
from savings.models import SavingsRecord
from savings.selectors import monthly_savings_history, savings_summary
from subscriptions.models import Subscription, SubscriptionPayment, SubscriptionPlan

ZERO = Decimal("0")
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# --------------------------------------------------------------------------
# small formatting helpers
# --------------------------------------------------------------------------

def display_name(user: User) -> str:
    return user.get_full_name() if user else "—"


def short_name(user: User) -> str:
    """'Sarah N.' — what other members / merchants may see. Never a phone."""
    if not user:
        return "Member"
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if first and last:
        return f"{first} {last[0]}."
    return first or "Member"


def initials(text: str) -> str:
    parts = [p for p in (text or "").replace("-", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def time_ago(dt) -> str:
    if not dt:
        return "—"
    delta = timezone.now() - dt
    secs = int(delta.total_seconds())
    if secs < 0:
        return "soon"
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 86400:
        return f"{secs // 3600} hr ago"
    if secs < 86400 * 2:
        return "Yesterday"
    if secs < 86400 * 14:
        return f"{secs // 86400} days ago"
    return timezone.localtime(dt).strftime("%d %b %Y")


def clock_label(dt) -> str:
    """'6:05 PM'. Built by hand: strftime's "no zero padding" flag is Linux/macOS-only and
    raises "Invalid format string" on Windows, so never use it."""
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def when_label(dt) -> str:
    """Expiry-style label: 'Today, 6:00 PM' / 'Tomorrow' / 'in 3 days'."""
    if not dt:
        return "—"
    now = timezone.localtime()
    local = timezone.localtime(dt)
    if local < now:
        return "Expired"
    days = (local.date() - now.date()).days
    clock = clock_label(local)
    if days == 0:
        return f"Today, {clock}"
    if days == 1:
        return f"Tomorrow, {clock}"
    return f"{local.strftime('%d %b')}, {clock}"


def short_date(dt) -> str:
    return timezone.localtime(dt).strftime("%d %b %Y") if dt else "—"


def clock_or_day(dt) -> str:
    if not dt:
        return "—"
    local = timezone.localtime(dt)
    if local.date() == timezone.localdate():
        return clock_label(local)
    if local.date() == timezone.localdate() - timedelta(days=1):
        return "Yesterday"
    return local.strftime("%d %b")


def pct_change(new, old):
    if not old:
        return None
    return round((float(new) - float(old)) / float(old) * 100, 1)


def _haversine_km(a: Area, b: Area):
    if None in (a.latitude, a.longitude, b.latitude, b.longitude):
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (float(a.latitude), float(a.longitude), float(b.latitude), float(b.longitude)))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def distance_label(origin: Area | None, target: Area) -> str:
    if origin is None:
        return target.name
    if origin.pk == target.pk:
        return "In your area"
    km = _haversine_km(origin, target)
    return f"{km:.1f}km away" if km is not None else target.name


def _month_start(now=None):
    now = now or timezone.localtime()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _day_start(now=None):
    now = now or timezone.localtime()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def last_n_months(n: int):
    """[(year, month, label)] oldest-first, ending with the current month."""
    now = timezone.localtime()
    out = []
    for i in range(n - 1, -1, -1):
        year, month = now.year, now.month - i
        while month < 1:
            month += 12
            year -= 1
        out.append((year, month, MONTH_NAMES[month - 1]))
    return out


def areas_active():
    return list(Area.objects.filter(is_active=True).order_by("name"))


# --------------------------------------------------------------------------
# offers (shared by landing + member)
# --------------------------------------------------------------------------

def live_offers_qs():
    """Offers a member can actually claim right now. A suspended or
    unverified merchant's offers never appear, even if the Offer row is
    still marked ACTIVE."""
    return Offer.objects.filter(
        status=Offer.Status.ACTIVE,
        expires_at__gt=timezone.now(),
        quantity__gt=0,
        merchant__status=Merchant.Status.VERIFIED,
    ).select_related("merchant", "category", "area").prefetch_related("images")


def _offer_card(offer: Offer, origin: Area | None = None) -> dict:
    badges = []
    if origin is not None and offer.area_id == origin.pk:
        badges.append("In your area")
    if offer.quantity <= 5:
        badges.append("Limited stock")
    if (offer.expires_at - timezone.now()) <= timedelta(hours=3):
        badges.append("Expires soon")
    badges.append("Verified seller")
    return {
        "id": offer.pk,
        "item": offer.item_name,
        "normal": offer.normal_price,
        "member": offer.member_price,
        "saving": offer.possible_saving,
        "seller": offer.merchant.business_name,
        "vendorType": offer.merchant.vendor_type or offer.category.label,
        "area": offer.area.name,
        "distance": distance_label(origin, offer.area),
        "same_area": bool(origin is not None and offer.area_id == origin.pk),
        "category": offer.category.label,
        "emoji": offer.category.emoji or "🏷️",
        "stock": offer.quantity,
        "expires": when_label(offer.expires_at),
        "delivery": offer.delivery_available,
        "phone": offer.merchant.phone,
        "whatsapp": "".join(ch for ch in (offer.merchant.whatsapp or offer.merchant.phone or "") if ch.isdigit()),
        "badges": badges,
        "photo": _primary_photo(offer),
    }


def _primary_photo(offer: Offer) -> str:
    imgs = list(offer.images.all())  # prefetched where possible
    if not imgs:
        return ""
    img = next((i for i in imgs if i.is_primary), imgs[0])
    try:
        return img.image.url
    except ValueError:
        return ""


def landing_context() -> dict:
    now = timezone.now()
    offers = list(live_offers_qs().order_by("-visibility_score", "-created_at")[:6])
    # (the platform owner's own auto-created merchant profile is not a real seller: keep it out of the public number)
    verified = Merchant.objects.filter(status=Merchant.Status.VERIFIED, user__is_superuser=False).count()
    area_rows = []
    for area in Area.objects.filter(is_active=True, is_launch_area=True).order_by("name"):
        area_rows.append(area.name)
    strength = merchant_strength_map(limit_areas=6)
    plan = SubscriptionPlan.objects.filter(is_active=True).order_by("price").first()
    return {
        "live_local_deals": [_offer_card(o) for o in offers],
        "launch_areas": area_rows,
        "merchant_strength_map": strength,
        "search_categories": [
            {"key": c.key, "label": c.label, "emoji": c.emoji or "🏷️"} for c in OfferCategory.objects.filter(is_active=True)
        ],
        "stats": {
            "verified_sellers": verified,
            "launch_area_count": len(area_rows),
            "active_offers": live_offers_qs().count(),
            "members": Member.objects.count(),
            "plan_price": plan.price if plan else None,
            "plan_label": plan.label if plan else "",
            "top_saving": max((o.possible_saving for o in offers), default=None),
        },
    }


def merchant_strength_map(limit_areas: int | None = None):
    """Per area: the categories with the most live offers right now."""
    rows = (
        live_offers_qs()
        .values("area__name", "category__label")
        .annotate(n=Count("id"))
        .order_by("area__name", "-n")
    )
    grouped: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if len(grouped[r["area__name"]]) < 3:
            grouped[r["area__name"]].append(r["category__label"])
    out = [{"area": a, "bestOn": cats} for a, cats in grouped.items()]
    return out[:limit_areas] if limit_areas else out


# --------------------------------------------------------------------------
# MEMBER
# --------------------------------------------------------------------------

SORTS = {
    "nearest": "Nearest",
    "cheapest": "Cheapest",
    "saving": "Biggest saving",
}


def member_context(user: User, params) -> dict | None:
    member = Member.objects.select_related("user", "area").filter(user=user).first()
    if member is None:
        return None

    now = timezone.now()
    month_start = _month_start()

    # ---- subscription ----------------------------------------------------
    subscription = Subscription.objects.select_related("plan").filter(member=member).order_by("-created_at").first()
    pending_payment = SubscriptionPayment.objects.filter(
        subscription__member=member, status=SubscriptionPayment.Status.PENDING
    ).exists()
    paid_this_month = (
        SubscriptionPayment.objects.filter(
            subscription__member=member, status=SubscriptionPayment.Status.SUCCESS, created_at__gte=month_start
        ).aggregate(t=Sum("amount"))["t"]
        or ZERO
    )
    default_plan = SubscriptionPlan.objects.filter(is_active=True).order_by("price").first()
    last_provider_payment = (
        Payment.objects.filter(user=user, purpose=Payment.Purpose.SUBSCRIPTION, status=Payment.Status.SUCCESS)
        .order_by("-created_at")
        .first()
    )
    sub_ctx = {
        "exists": subscription is not None,
        "active": bool(subscription and subscription.is_currently_active),
        "status": subscription.status if subscription else "none",
        "status_label": subscription.get_status_display() if subscription else "No subscription",
        "plan_label": subscription.plan.label if subscription else (default_plan.label if default_plan else ""),
        "price": subscription.plan.price if subscription else (default_plan.price if default_plan else None),
        "period_days": subscription.plan.period_days if subscription else (default_plan.period_days if default_plan else None),
        "renews_on": short_date(subscription.current_period_end) if subscription and subscription.current_period_end else None,
        "method": last_provider_payment.get_method_display() if last_provider_payment else None,
        "pending_payment": pending_payment,
    }

    # ---- savings ---------------------------------------------------------
    summary = savings_summary(member)
    history = monthly_savings_history(member, 6)
    savings = {
        "paid_this_month": paid_this_month,
        "confirmed_month": summary["confirmed_this_month"],
        "confirmed_total": summary["confirmed_total"],
        "possible": summary["possible_total"],
        "net_benefit": summary["confirmed_this_month"] - paid_this_month,
        "redeemed_count": summary["claims_count"],
    }
    savings_months = [MONTH_NAMES[h["month"] - 1] for h in history]
    savings_values = [float(h["saved"]) for h in history]

    # ---- offers (search / filter / sort) ---------------------------------
    q = (params.get("q") or "").strip()[:80]
    cat = (params.get("cat") or "").strip()
    sort = params.get("sort") if params.get("sort") in SORTS else "nearest"
    only_delivery = params.get("delivery") == "1"
    only_my_area = params.get("here") == "1"

    qs = live_offers_qs()
    if q:
        qs = qs.filter(Q(item_name__icontains=q) | Q(merchant__business_name__icontains=q) | Q(category__label__icontains=q))
    if cat:
        qs = qs.filter(category__key=cat)
    if only_delivery:
        qs = qs.filter(delivery_available=True)
    if only_my_area:
        qs = qs.filter(area=member.area)

    qs = qs.annotate(
        _here=Case(When(area_id=member.area_id, then=Value(0)), default=Value(1), output_field=IntegerField()),
        _saving=F("normal_price") - F("member_price"),
    )
    if sort == "cheapest":
        qs = qs.order_by("member_price", "_here")
    elif sort == "saving":
        qs = qs.order_by("-_saving", "_here")
    else:
        qs = qs.order_by("_here", "-visibility_score", "member_price")

    found = list(qs[:48])
    cards = [_offer_card(o, member.area) for o in found]
    searching = bool(q or cat or only_delivery or only_my_area)

    nearby_deals = [c for c in cards if c["same_area"]][:6] or cards[:6]
    basket_qs = (
        live_offers_qs().filter(area=member.area).order_by("-visibility_score", "member_price")[:8]
    )
    basket_items = [_offer_card(o, member.area) for o in basket_qs]

    # ---- compare same item across sellers ---------------------------------
    compare_options = list(
        live_offers_qs()
        .values("item_name")
        .annotate(sellers=Count("merchant", distinct=True))
        .order_by("-sellers", "item_name")[:30]
    )
    compare_item = (params.get("compare") or "").strip()
    if not compare_item:
        for opt in compare_options:
            if opt["sellers"] >= 2:
                compare_item = opt["item_name"]
                break
        if not compare_item and compare_options:
            compare_item = compare_options[0]["item_name"]
    compare_rows = []
    if compare_item:
        for o in live_offers_qs().filter(item_name__iexact=compare_item).order_by("member_price")[:8]:
            compare_rows.append(_offer_card(o, member.area))

    # ---- claims ------------------------------------------------------------
    claim_qs = (
        OfferClaim.objects.filter(member=member)
        .select_related("offer", "offer__merchant", "delivery_job")
        .order_by("-created_at")[:20]
    )
    claimed_offers = []
    for c in claim_qs:
        status = c.status
        if status == OfferClaim.Status.CLAIMED and c.is_expired:
            status = OfferClaim.Status.EXPIRED
        claimed_offers.append({
            "id": c.pk,
            "item": c.offer.item_name,
            "code": c.code,
            "seller": c.offer.merchant.business_name,
            "expires": when_label(c.expires_at) if status == OfferClaim.Status.CLAIMED else short_date(c.expires_at),
            "saving": c.expected_saving,
            "status": status,
            "status_label": dict(OfferClaim.Status.choices).get(status, status),
            "can_cancel": status == OfferClaim.Status.CLAIMED,
            "has_delivery": hasattr(c, "delivery_job"),
            "delivery_offered": c.offer.delivery_available,
        })
    deliverable_claims = [c for c in claimed_offers if c["status"] == OfferClaim.Status.CLAIMED and not c["has_delivery"]]

    # ---- deliveries --------------------------------------------------------
    my_deliveries = [
        {
            "id": j.pk,
            "merchant": j.pickup_merchant.business_name,
            "to": f"{j.dropoff_address}, {j.dropoff_area.name}",
            "status": j.get_status_display(),
            "fare": j.fare,
            "type": j.get_delivery_type_display(),
        }
        for j in DeliveryJob.objects.filter(claim__member=member)
        .select_related("pickup_merchant", "dropoff_area")
        .order_by("-created_at")[:5]
    ]
    open_routes = [
        {
            "label": f"{r.origin_area.name} → {r.destination_area.name}",
            "departs": when_label(r.departure_time),
            "free": max(r.max_packages - r.packages.count(), 0),
        }
        for r in SharedRoute.objects.filter(status=SharedRoute.Status.PUBLISHED, departure_time__gt=now)
        .select_related("origin_area", "destination_area")
        .order_by("departure_time")[:3]
    ]

    # ---- item requests -----------------------------------------------------
    area_requests = (
        MemberRequest.objects.filter(area=member.area, status__in=[MemberRequest.Status.OPEN, MemberRequest.Status.RESPONDED])
        .select_related("member__user")
        .annotate(n=Count("responses"))
        .order_by("-created_at")[:6]
    )
    member_requests = [
        {
            "id": r.pk,
            "item": r.item_name,
            "who": "You" if r.member_id == member.pk else short_name(r.member.user),
            "mine": r.member_id == member.pk,
            "area": member.area.name,
            "when": time_ago(r.created_at),
            "responses": r.n,
            "status": r.get_status_display(),
        }
        for r in area_requests
    ]

    # ---- referrals ---------------------------------------------------------
    rewards = ReferralReward.objects.filter(referrer=member).aggregate(
        pending=Sum("amount", filter=Q(status=ReferralReward.Status.PENDING)),
        credited=Sum("amount", filter=Q(status=ReferralReward.Status.CREDITED)),
    )
    referral = {
        "code": member.referral_code,
        "joined": member.referrals.count(),
        "paying": ReferralReward.objects.filter(referrer=member).count(),
        "pending": rewards["pending"] or ZERO,
        "credited": rewards["credited"] or ZERO,
    }

    complaints = [
        {"id": c.pk, "subject": c.subject, "status": c.get_status_display(), "when": time_ago(c.created_at)}
        for c in Complaint.objects.filter(member=member).order_by("-created_at")[:5]
    ]

    return {
        "member": member,
        "sub": sub_ctx,
        "savings": savings,
        "savings_months": savings_months,
        "savings_values": savings_values,
        "has_savings_history": any(v for v in savings_values),
        "search": {"q": q, "cat": cat, "sort": sort, "delivery": only_delivery, "here": only_my_area, "active": searching},
        "sorts": SORTS,
        "search_categories": [
            {"key": c.key, "label": c.label, "emoji": c.emoji or "🏷️"} for c in OfferCategory.objects.filter(is_active=True)
        ],
        "results": cards,
        "nearby_deals": nearby_deals,
        "basket_items": basket_items,
        "compare_item": compare_item,
        "compare_options": compare_options,
        "compare_rows": compare_rows,
        "claimed_offers": claimed_offers,
        "deliverable_claims": deliverable_claims,
        "my_deliveries": my_deliveries,
        "open_routes": open_routes,
        "member_requests": member_requests,
        "referral": referral,
        "complaints": complaints,
        "areas": areas_active(),
    }


# --------------------------------------------------------------------------
# MERCHANT
# --------------------------------------------------------------------------

def merchant_context(user: User) -> dict | None:
    merchant = (
        Merchant.objects.select_related("user", "area", "category", "verified_by").filter(user=user).first()
    )
    if merchant is None:
        return None

    now = timezone.now()
    month_start = _month_start()
    week_ago = now - timedelta(days=7)

    offers_qs = (
        Offer.objects.filter(merchant=merchant)
        .select_related("category", "area")
        .annotate(claim_count=Count("claims", distinct=True))
        .order_by("-created_at")
    )
    offers = []
    for o in offers_qs[:50]:
        status = o.status
        if status == Offer.Status.ACTIVE and o.is_expired:
            status = Offer.Status.EXPIRED
        offers.append({
            "id": o.pk,
            "item": o.item_name,
            "normal": o.normal_price,
            "member": o.member_price,
            "qty": o.quantity,
            "expires": when_label(o.expires_at),
            "views": o.views_count,
            "claims": o.claim_count,
            "status": status,
            "status_label": dict(Offer.Status.choices).get(status, status),
            "can_pause": status == Offer.Status.ACTIVE,
            "can_delete": o.claim_count == 0,
        })

    claims_qs = OfferClaim.objects.filter(offer__merchant=merchant)
    claims = []
    for c in claims_qs.select_related("offer", "member__user").order_by("-created_at")[:30]:
        status = c.status
        if status == OfferClaim.Status.CLAIMED and c.is_expired:
            status = OfferClaim.Status.EXPIRED
        # The full code is a secret that proves the customer is standing in
        # front of you — we never print it for an unredeemed claim.
        masked = c.code if status == OfferClaim.Status.REDEEMED else f"{c.code[:3]}••{c.code[-2:]}"
        claims.append({
            "code": masked,
            "member": short_name(c.member.user),
            "item": c.offer.item_name,
            "status": status,
            "status_label": dict(OfferClaim.Status.choices).get(status, status),
            "time": clock_or_day(c.redeemed_at or c.created_at),
        })

    claim_stats = claims_qs.filter(created_at__gte=month_start).aggregate(
        total=Count("id"), redeemed=Count("id", filter=Q(status=OfferClaim.Status.REDEEMED))
    )
    sales = (
        SavingsRecord.objects.filter(merchant=merchant, created_at__gte=month_start).aggregate(t=Sum("member_price"))["t"]
        or ZERO
    )
    interactions = {
        r["kind"]: r["n"]
        for r in OfferInteraction.objects.filter(offer__merchant=merchant, created_at__gte=week_ago)
        .values("kind")
        .annotate(n=Count("id"))
    }
    total_views = Offer.objects.filter(merchant=merchant).aggregate(t=Sum("views_count"))["t"] or 0
    conv = round(100 * claim_stats["redeemed"] / claim_stats["total"]) if claim_stats["total"] else None

    delivery_jobs = [
        {
            "id": j.pk,
            "to": f"{j.dropoff_address}, {j.dropoff_area.name}",
            "status": j.get_status_display(),
            "fare": j.fare,
            "type": j.get_delivery_type_display(),
        }
        for j in DeliveryJob.objects.filter(pickup_merchant=merchant).select_related("dropoff_area").order_by("-created_at")[:6]
    ]
    delivery_count = DeliveryJob.objects.filter(pickup_merchant=merchant, created_at__gte=month_start).count()

    area_requests = [
        {
            "id": r.pk,
            "item": r.item_name,
            "description": r.description,
            "budget": r.max_budget,
            "when": time_ago(r.created_at),
            "responded": r.responses.filter(merchant=merchant).exists(),
        }
        for r in MemberRequest.objects.filter(
            area=merchant.area, status__in=[MemberRequest.Status.OPEN, MemberRequest.Status.RESPONDED]
        ).order_by("-created_at")[:6]
    ]

    packages = list(PromotionPackage.objects.filter(is_active=True).order_by("price"))
    promo_offers = [o for o in offers if o["status"] == Offer.Status.ACTIVE]

    return {
        "merchant": merchant,
        "initials": initials(merchant.business_name),
        "verified_by": display_name(merchant.verified_by) if merchant.verified_by else None,
        "verified_on": short_date(merchant.verified_at) if merchant.verified_at else None,
        "stats": {
            "views": total_views,
            "claims_month": claim_stats["total"],
            "redeemed_month": claim_stats["redeemed"],
            "conversion": conv,
            "sales_month": sales,
            "calls": interactions.get(OfferInteraction.Kind.CALL, 0),
            "whatsapp": interactions.get(OfferInteraction.Kind.WHATSAPP, 0),
            "delivery_clicks": interactions.get(OfferInteraction.Kind.DELIVERY_REQUEST_CLICK, 0),
            "deliveries_month": delivery_count,
            "active_offers": sum(1 for o in offers if o["status"] == Offer.Status.ACTIVE),
        },
        "offers": offers,
        "claims": claims,
        "delivery_jobs": delivery_jobs,
        "area_requests": area_requests,
        "packages": packages,
        "promo_offers": promo_offers,
        "categories": list(OfferCategory.objects.filter(is_active=True)),
        "areas": areas_active(),
        "packaging_choices": Offer.PackagingStatus.choices,
        "can_post": merchant.status == Merchant.Status.VERIFIED,
    }


# --------------------------------------------------------------------------
# RIDER
# --------------------------------------------------------------------------

def rider_context(user: User) -> dict | None:
    from payments.services.withdrawal_flow import available_rider_balance

    rider = Rider.objects.select_related("user", "area").filter(user=user).first()
    if rider is None:
        return None

    now = timezone.now()
    today = _day_start()
    week_ago = now - timedelta(days=7)

    from django.urls import reverse

    ACTION_FOR_STATUS = {
        DeliveryJob.Status.REQUESTED: ("accept", "Accept job"),
        DeliveryJob.Status.ACCEPTED: ("arrived", "Arrived at seller"),
        DeliveryJob.Status.ARRIVED_AT_SELLER: ("picked-up", "Picked up"),
        DeliveryJob.Status.PICKED_UP: ("on-route", "On route"),
        DeliveryJob.Status.ON_ROUTE: ("delivered", "Confirm delivery"),
    }
    ACTION_URL_NAME = {
        "accept": "deliveries:accept_job", "arrived": "deliveries:arrived_job",
        "picked-up": "deliveries:picked_up_job", "on-route": "deliveries:on_route_job",
        "delivered": "deliveries:delivered_job",
    }

    job_qs = (
        DeliveryJob.objects.filter(Q(rider=rider, created_at__gte=today - timedelta(days=2)) | Q(rider=rider, status__in=DeliveryJob.ACTIVE_STATUSES) | Q(rider__isnull=True, status=DeliveryJob.Status.REQUESTED))
        .select_related("pickup_merchant", "dropoff_area", "claim__offer")
        .distinct()
        .order_by("-created_at")[:40]
    )
    jobs = []
    for j in job_qs:
        action = ACTION_FOR_STATUS.get(j.status)
        mine = j.rider_id == rider.pk
        jobs.append({
            "id": j.pk,
            "ref": f"JOB-{j.pk}",
            "from": j.pickup_merchant.business_name,
            "to": f"{j.dropoff_address}, {j.dropoff_area.name}",
            "item": j.claim.offer.item_name if j.claim_id and j.claim.offer_id else "Parcel",
            "fare": j.fare,
            "status": j.get_status_display(),
            "status_key": j.status,
            "type": j.get_delivery_type_display(),
            "action": action[0] if action and (mine or j.status == DeliveryJob.Status.REQUESTED) else None,
            "action_label": action[1] if action else None,
            "action_url": reverse(ACTION_URL_NAME[action[0]], args=[j.pk]) if action and (mine or j.status == DeliveryJob.Status.REQUESTED) else None,
            "fail_url": reverse("deliveries:failed_job", args=[j.pk]),
            "needs_otp": j.status == DeliveryJob.Status.ON_ROUTE,
            "can_fail": mine and j.status in DeliveryJob.ACTIVE_STATUSES,
            "mine": mine,
        })

    today_jobs = DeliveryJob.objects.filter(rider=rider, created_at__gte=today)
    completed_today = DeliveryJob.objects.filter(rider=rider, status=DeliveryJob.Status.DELIVERED, delivered_at__gte=today).count()
    pending_pickup = DeliveryJob.objects.filter(
        rider=rider, status__in=[DeliveryJob.Status.ACCEPTED, DeliveryJob.Status.ARRIVED_AT_SELLER]
    ).count()
    earn_today = RiderEarning.objects.filter(rider=rider, created_at__gte=today).aggregate(
        gross=Sum("gross_amount"), commission=Sum("commission_amount"), net=Sum("net_amount")
    )
    earn_week = RiderEarning.objects.filter(rider=rider, created_at__gte=week_ago).aggregate(
        gross=Sum("gross_amount"), commission=Sum("commission_amount"), net=Sum("net_amount"), n=Count("id")
    )
    failed_week = DeliveryJob.objects.filter(rider=rider, status=DeliveryJob.Status.FAILED, failed_at__gte=week_ago).count()
    lifetime_jobs = DeliveryJob.objects.filter(rider=rider, status=DeliveryJob.Status.DELIVERED).count()

    routes = []
    for r in (
        SharedRoute.objects.filter(rider=rider)
        .select_related("origin_area", "destination_area")
        .annotate(pkg=Count("packages"))
        .order_by("-departure_time")[:6]
    ):
        routes.append({
            "id": r.pk,
            "name": f"{r.origin_area.name} → {r.destination_area.name}",
            "departs": when_label(r.departure_time) if r.departure_time > now else short_date(r.departure_time),
            "packages": r.pkg,
            "max": r.max_packages,
            "status": r.status,
            "status_label": r.get_status_display(),
            "can_publish": r.status == SharedRoute.Status.DRAFT,
            "can_complete": r.status in (SharedRoute.Status.PUBLISHED, SharedRoute.Status.IN_PROGRESS),
            "can_cancel": r.status in (SharedRoute.Status.DRAFT, SharedRoute.Status.PUBLISHED),
        })
    featured_route = None
    route_obj = (
        SharedRoute.objects.filter(rider=rider, status__in=[SharedRoute.Status.PUBLISHED, SharedRoute.Status.IN_PROGRESS])
        .select_related("origin_area", "destination_area")
        .order_by("departure_time")
        .first()
    )
    if route_obj:
        route_earn = RiderEarning.objects.filter(delivery_job__route=route_obj).aggregate(
            gross=Sum("gross_amount"), commission=Sum("commission_amount"), net=Sum("net_amount")
        )
        featured_route = {
            "name": f"{route_obj.origin_area.name} → {route_obj.destination_area.name}",
            "packages": route_obj.packages.count(),
            "gross": route_earn["gross"] or ZERO,
            "commission": route_earn["commission"] or ZERO,
            "net": route_earn["net"] or ZERO,
            "departs": when_label(route_obj.departure_time),
        }

    withdrawals = [
        {"amount": w.amount, "net": w.net_amount, "status": w.get_status_display(), "when": time_ago(w.created_at), "phone": w.phone}
        for w in Withdrawal.objects.filter(user=user).order_by("-created_at")[:5]
    ]

    return {
        "rider": rider,
        "initials": initials(display_name(user)),
        "jobs": jobs,
        "stats": {
            "today_jobs": today_jobs.count(),
            "pending_pickup": pending_pickup,
            "completed_today": completed_today,
            "gross_today": earn_today["gross"] or ZERO,
            "net_today": earn_today["net"] or ZERO,
            "commission_today": earn_today["commission"] or ZERO,
        },
        "week": {
            "gross": earn_week["gross"] or ZERO,
            "commission": earn_week["commission"] or ZERO,
            "net": earn_week["net"] or ZERO,
            "delivered": earn_week["n"] or 0,
            "failed": failed_week,
        },
        "lifetime_jobs": lifetime_jobs,
        "balance": available_rider_balance(rider),
        "withdrawals": withdrawals,
        "routes": routes,
        "route_today": featured_route,
        "areas": areas_active(),
        "verified": rider.status == Rider.Status.VERIFIED,
    }


# --------------------------------------------------------------------------
# AGENT
# --------------------------------------------------------------------------

def agent_context(user: User) -> dict | None:
    agent = Agent.objects.select_related("user").filter(user=user).first()
    if agent is None:
        return None

    now = timezone.now()
    today = _day_start()
    month_start = _month_start()
    thirty_days = now - timedelta(days=30)
    areas = list(agent.areas.order_by("name"))
    area_ids = [a.pk for a in areas]

    merchants_to_verify = [
        {"id": m.pk, "name": m.business_name, "area": m.area.name, "category": m.category.label, "contact": m.phone or "—", "submitted": time_ago(m.created_at)}
        for m in Merchant.objects.filter(area_id__in=area_ids, status=Merchant.Status.PENDING)
        .select_related("area", "category")
        .order_by("created_at")
    ]
    riders_to_verify = [
        {"id": r.pk, "name": display_name(r.user), "area": r.area.name, "vehicle": r.get_vehicle_type_display(), "plate": r.plate_number or "—", "contact": r.user.phone, "submitted": time_ago(r.created_at),
         "docs": [{"id": d.pk, "label": d.get_doc_type_display()} for d in r.documents.all()]}
        for r in Rider.objects.filter(area_id__in=area_ids, status=Rider.Status.PENDING).select_related("area", "user").prefetch_related("documents").order_by("created_at")
    ]
    offers_to_approve = [
        {"id": o.pk, "item": o.item_name, "merchant": o.merchant.business_name, "area": o.area.name, "normal": o.normal_price, "member": o.member_price, "qty": o.quantity}
        for o in Offer.objects.filter(area_id__in=area_ids, status=Offer.Status.PENDING).select_related("merchant", "area").order_by("created_at")
    ]
    complaints = [
        {
            "id": c.pk,
            "member": short_name(c.member.user),
            "area": c.area.name,
            "subject": c.subject,
            "description": c.description[:160],
            "status": c.status,
            "status_label": c.get_status_display(),
            "can_start": c.status == Complaint.Status.OPEN,
            "when": time_ago(c.created_at),
        }
        for c in Complaint.objects.filter(
            area_id__in=area_ids, status__in=[Complaint.Status.OPEN, Complaint.Status.INVESTIGATING, Complaint.Status.ESCALATED]
        )
        .select_related("member__user", "area")
        .order_by("created_at")[:15]
    ]

    # price sheet: the last price this agent recorded per (item, area) so
    # they can see what changed; plus blank rows to add new items.
    latest = {}
    for p in PriceRecord.objects.filter(area_id__in=area_ids).select_related("area", "category").order_by("-created_at")[:300]:
        key = (p.item_name.lower(), p.area_id)
        if key not in latest:
            latest[key] = p
    price_collection = [
        {"item": p.item_name, "area": p.area.name, "area_id": p.area_id, "category_id": p.category_id, "category": p.category.label, "lastPrice": p.price}
        for p in list(latest.values())[:12]
    ]

    verified_merchants = Merchant.objects.filter(verified_by=user, status=Merchant.Status.VERIFIED).count()
    verified_riders = Rider.objects.filter(verified_by=user, status=Rider.Status.VERIFIED).count()
    prices_today = PriceRecord.objects.filter(agent=agent, created_at__gte=today).count()
    earnings_total = AgentEarning.objects.filter(agent=agent).aggregate(t=Sum("amount"))["t"] or ZERO
    earnings_month = AgentEarning.objects.filter(agent=agent, created_at__gte=month_start).aggregate(t=Sum("amount"))["t"] or ZERO
    by_source = {
        r["source"]: r["t"]
        for r in AgentEarning.objects.filter(agent=agent, created_at__gte=month_start).values("source").annotate(t=Sum("amount"))
    }

    area_perf = {
        "members": Member.objects.filter(area_id__in=area_ids).count(),
        "merchants": Merchant.objects.filter(area_id__in=area_ids, status=Merchant.Status.VERIFIED).count(),
        "riders": Rider.objects.filter(area_id__in=area_ids, status=Rider.Status.VERIFIED).count(),
        "savings_30d": SavingsRecord.objects.filter(member__area_id__in=area_ids, created_at__gte=thirty_days).aggregate(t=Sum("saving_amount"))["t"] or ZERO,
        "prices_30d": PriceRecord.objects.filter(agent=agent, created_at__gte=thirty_days).count(),
    }

    return {
        "agent": agent,
        "areas": areas,
        "all_areas": areas_active(),
        "categories": list(OfferCategory.objects.filter(is_active=True)),
        "merchants_to_verify": merchants_to_verify,
        "riders_to_verify": riders_to_verify,
        "offers_to_approve": offers_to_approve,
        "complaints": complaints,
        "price_collection": price_collection,
        "tasks": [
            {"id": tk.pk, "title": tk.title, "kind": tk.get_kind_display(), "description": tk.description,
             "area": tk.area.name if tk.area else "", "due": when_label(tk.due_at) if tk.due_at else "",
             "overdue": bool(tk.due_at and tk.due_at < timezone.now())}
            for tk in AgentTask.objects.filter(agent=agent, status=AgentTask.Status.OPEN).select_related("area")[:20]
        ],
        "stats": {
            "verified_merchants": verified_merchants,
            "verified_riders": verified_riders,
            "prices_today": prices_today,
            "open_complaints": len(complaints),
            "pending_total": len(merchants_to_verify) + len(riders_to_verify) + len(offers_to_approve),
        },
        "earnings": {
            "total": earnings_total,
            "month": earnings_month,
            "merchant_fees": by_source.get(AgentEarning.Source.MERCHANT_VERIFICATION, ZERO),
            "rider_fees": by_source.get(AgentEarning.Source.RIDER_VERIFICATION, ZERO),
        },
        "area_perf": area_perf,
        "merchant_checklist": [
            ("real_person_met", "Real person met in person"),
            ("phone_confirmed", "Phone number confirmed"),
            ("location_confirmed", "Exact location confirmed"),
            ("stock_photo_taken", "Stock photo taken today"),
            ("current_prices_checked", "Prices match current area"),
            ("packaging_hygiene_ok", "Clean packaging / hygiene"),
            ("duplicate_account_check_passed", "No duplicate seller account"),
        ],
        "rider_checklist": [
            ("real_person_met", "Real person met in person"),
            ("id_checked", "National ID checked"),
            ("permit_checked", "Driving permit checked"),
            ("vehicle_checked", "Vehicle / plate checked"),
        ],
    }


# --------------------------------------------------------------------------
# ADMIN
# --------------------------------------------------------------------------

def _status_label_for_member(member: Member, sub: Subscription | None) -> str:
    if member.account_status == Member.AccountStatus.SUSPENDED or not member.user.is_active:
        return "Suspended"
    if sub and sub.is_currently_active:
        return "Active"
    if sub and sub.status == Subscription.Status.PAUSED:
        return "Paused"
    if sub:
        return "Expired"
    return "No subscription"


def admin_overview() -> dict:
    now = timezone.now()
    today = _day_start()
    month_start = _month_start()
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)

    members_total = Member.objects.count()
    members_this_month = Member.objects.filter(created_at__gte=month_start).count()
    active_subs = Subscription.objects.filter(status=Subscription.Status.ACTIVE, current_period_end__gt=now).count()
    merchants = Merchant.objects.aggregate(
        verified=Count("id", filter=Q(status=Merchant.Status.VERIFIED)),
        pending=Count("id", filter=Q(status=Merchant.Status.PENDING)),
    )
    riders = Rider.objects.aggregate(
        verified=Count("id", filter=Q(status=Rider.Status.VERIFIED)),
        pending=Count("id", filter=Q(status=Rider.Status.PENDING)),
    )
    agents_active = Agent.objects.filter(status=Agent.Status.ACTIVE, user__is_active=True).count()
    covered = Area.objects.filter(is_active=True, agents__status=Agent.Status.ACTIVE).distinct().count()
    active_areas = Area.objects.filter(is_active=True).count()
    offers = Offer.objects.aggregate(
        active=Count("id", filter=Q(status=Offer.Status.ACTIVE, expires_at__gt=now)),
        pending=Count("id", filter=Q(status=Offer.Status.PENDING)),
        reported=Count("id", filter=Q(status=Offer.Status.REPORTED)),
    )
    confirmed = SavingsRecord.objects.aggregate(t=Sum("saving_amount"))["t"] or ZERO
    possible = ZERO
    for o in Offer.objects.filter(status=Offer.Status.ACTIVE, expires_at__gt=now, quantity__gt=0):
        possible += o.possible_saving * o.quantity
    pay_today = Payment.objects.filter(status=Payment.Status.SUCCESS, created_at__gte=today).aggregate(t=Sum("amount"), n=Count("id"))
    failed_30d = Payment.objects.filter(status=Payment.Status.FAILED, created_at__gte=now - timedelta(days=30)).count()
    commission = RiderEarning.objects.aggregate(t=Sum("commission_amount"))["t"] or ZERO
    complaints_open = Complaint.objects.filter(
        status__in=[Complaint.Status.OPEN, Complaint.Status.INVESTIGATING, Complaint.Status.ESCALATED]
    ).count()
    complaints_escalated = Complaint.objects.filter(status=Complaint.Status.ESCALATED).count()

    stats = {
        "members_total": members_total,
        "members_this_month": members_this_month,
        "active_subs": active_subs,
        "retention": round(100 * active_subs / members_total, 1) if members_total else None,
        "merchants_verified": merchants["verified"],
        "merchants_pending": merchants["pending"],
        "riders_verified": riders["verified"],
        "riders_pending": riders["pending"],
        "agents_active": agents_active,
        "areas_uncovered": max(active_areas - covered, 0),
        "offers_active": offers["active"],
        "offers_pending": offers["pending"],
        "offers_reported": offers["reported"],
        "confirmed": confirmed,
        "possible": possible,
        "pay_today": pay_today["t"] or ZERO,
        "pay_today_n": pay_today["n"] or 0,
        "failed_30d": failed_30d,
        "commission": commission,
        "complaints_open": complaints_open,
        "complaints_escalated": complaints_escalated,
    }

    # ---- charts -------------------------------------------------------------
    months = last_n_months(10)
    joined = {
        (r["m"].year, r["m"].month): r["n"]
        for r in Member.objects.annotate(m=TruncMonth("created_at")).values("m").annotate(n=Count("id"))
    }
    renewals = {
        (r["m"].year, r["m"].month): r["n"]
        for r in SubscriptionPayment.objects.filter(status=SubscriptionPayment.Status.SUCCESS)
        .annotate(m=TruncMonth("created_at"))
        .values("m")
        .annotate(n=Count("id"))
    }
    running = Member.objects.filter(created_at__lt=timezone.make_aware(__import__("datetime").datetime(months[0][0], months[0][1], 1))).count()
    growth_members, growth_renewals = [], []
    for y, m, _label in months:
        running += joined.get((y, m), 0)
        growth_members.append(running)
        growth_renewals.append(renewals.get((y, m), 0))
    charts = {
        "growth_months": [m[2] for m in months],
        "growth_members": growth_members,
        "growth_renewals": growth_renewals,
    }

    redeemed = list(
        OfferClaim.objects.filter(status=OfferClaim.Status.REDEEMED)
        .values("offer__category__label")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    charts["redemption_labels"] = [r["offer__category__label"] for r in redeemed]
    charts["redemption_values"] = [r["n"] for r in redeemed]
    sav = list(
        SavingsRecord.objects.values("claim__offer__category__label").annotate(t=Sum("saving_amount")).order_by("-t")
    )
    charts["savings_labels"] = [r["claim__offer__category__label"] for r in sav]
    charts["savings_values"] = [float(r["t"]) for r in sav]
    route = list(
        RiderEarning.objects.filter(delivery_job__route__isnull=False)
        .values("delivery_job__route__origin_area__name", "delivery_job__route__destination_area__name")
        .annotate(t=Sum("gross_amount"))
        .order_by("-t")[:5]
    )
    charts["route_labels"] = [f"{r['delivery_job__route__origin_area__name']}→{r['delivery_job__route__destination_area__name']}" for r in route]
    charts["route_values"] = [float(r["t"]) for r in route]
    by_status = list(Complaint.objects.values("status").annotate(n=Count("id")).order_by("-n"))
    label_for = dict(Complaint.Status.choices)
    charts["complaint_labels"] = [label_for.get(r["status"], r["status"]) for r in by_status]
    charts["complaint_values"] = [r["n"] for r in by_status]

    return {
        "stats": stats,
        "charts": charts,
        "risk_alerts": risk_alerts(),
        "recent_activity": recent_activity(),
        "pending_approvals": pending_approvals(),
        "area_launch_progress": area_launch_progress(),
        "supply_gaps": supply_gaps(),
        "price_movements": price_movements(limit=6),
        "merchant_strength_map": merchant_strength_map(),
    }


RISK_SEVERITY = {
    "login_lockout": "medium",
    "claim_redemption_locked": "high",
    "repeated_payment_failures": "medium",
}


def risk_alerts() -> list[dict]:
    alerts = []
    for ev in RiskEvent.objects.filter(reviewed=False).select_related("user").order_by("-created_at")[:6]:
        alerts.append({
            "kind": ev.event_type.replace("_", " ").capitalize(),
            "note": f"{display_name(ev.user) if ev.user else ev.ip_address or 'Unknown'} · {time_ago(ev.created_at)}",
            "severity": RISK_SEVERITY.get(ev.event_type, "low"),
        })
    now = timezone.now()
    failed_24h = Payment.objects.filter(status=Payment.Status.FAILED, created_at__gte=now - timedelta(hours=24)).count()
    if failed_24h:
        alerts.append({"kind": "Payment failed", "note": f"{failed_24h} failed payment(s) in the last 24h", "severity": "high" if failed_24h >= 10 else "low"})
    review = Payment.objects.filter(status=Payment.Status.REQUIRES_REVIEW).count()
    if review:
        alerts.append({"kind": "Payment needs review", "note": f"{review} payment(s) stuck after reconciliation timeout", "severity": "high"})
    stale = Offer.objects.filter(status=Offer.Status.ACTIVE, expires_at__lte=now).count()
    if stale:
        alerts.append({"kind": "Offer expired but still active", "note": f"{stale} offer(s) past expiry still marked active", "severity": "low"})
    reported = Offer.objects.filter(status=Offer.Status.REPORTED).count()
    if reported:
        alerts.append({"kind": "Reported offers", "note": f"{reported} offer(s) reported by members", "severity": "high"})
    overdue = Complaint.objects.filter(
        status__in=[Complaint.Status.OPEN, Complaint.Status.INVESTIGATING], created_at__lte=now - timedelta(hours=72)
    ).count()
    if overdue:
        alerts.append({"kind": "Complaints overdue", "note": f"{overdue} complaint(s) older than 72h", "severity": "medium"})
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(alerts, key=lambda a: order[a["severity"]])[:8]


def recent_activity(limit: int = 10) -> list[dict]:
    items = []
    for ev in ClaimEvent.objects.filter(event_type__in=["claimed", "redeemed"]).select_related(
        "claim__offer", "claim__member__user", "claim__member__area"
    ).order_by("-created_at")[:limit]:
        verb = "redeemed" if ev.event_type == "redeemed" else "claimed"
        items.append({
            "who": short_name(ev.claim.member.user),
            "what": f"{verb} “{ev.claim.offer.item_name}”",
            "where": ev.claim.member.area.name,
            "when": time_ago(ev.created_at),
            "ts": ev.created_at,
        })
    for p in Payment.objects.filter(status=Payment.Status.SUCCESS).select_related("user").order_by("-created_at")[:limit]:
        items.append({
            "who": short_name(p.user),
            "what": f"paid UGX {p.amount:,.0f} ({p.get_purpose_display().lower()})",
            "where": "Payments",
            "when": time_ago(p.created_at),
            "ts": p.created_at,
        })
    for j in DeliveryJob.objects.filter(status=DeliveryJob.Status.DELIVERED).select_related("rider__user", "dropoff_area").order_by("-delivered_at")[:limit]:
        items.append({
            "who": short_name(j.rider.user) if j.rider_id else "Rider",
            "what": f"delivered a package to {j.dropoff_area.name}",
            "where": j.dropoff_area.name,
            "when": time_ago(j.delivered_at),
            "ts": j.delivered_at or j.created_at,
        })
    for c in Complaint.objects.select_related("member__user", "area").order_by("-created_at")[:limit]:
        items.append({
            "who": short_name(c.member.user),
            "what": f"reported: {c.subject[:60]}",
            "where": c.area.name,
            "when": time_ago(c.created_at),
            "ts": c.created_at,
        })
    items.sort(key=lambda i: i["ts"], reverse=True)
    return items[:limit]


def pending_approvals() -> dict:
    merchants = [
        {"id": m.pk, "name": m.business_name, "area": m.area.name, "category": m.category.label, "submitted": time_ago(m.created_at)}
        for m in Merchant.objects.filter(status=Merchant.Status.PENDING).select_related("area", "category").order_by("created_at")[:8]
    ]
    riders = [
        {"id": r.pk, "name": display_name(r.user), "stage": r.get_vehicle_type_display(), "area": r.area.name, "submitted": time_ago(r.created_at)}
        for r in Rider.objects.filter(status=Rider.Status.PENDING).select_related("area", "user").order_by("created_at")[:8]
    ]
    offers = [
        {"id": o.pk, "item": o.item_name, "merchant": o.merchant.business_name, "normal": o.normal_price, "member": o.member_price}
        for o in Offer.objects.filter(status=Offer.Status.PENDING).select_related("merchant").order_by("created_at")[:8]
    ]
    return {"merchants": merchants, "riders": riders, "offers": offers}


def area_launch_progress() -> list[dict]:
    rows = []
    for a in (
        Area.objects.filter(is_active=True)
        .annotate(
            members_n=Count("members", distinct=True),
            merchants_n=Count("merchants", filter=Q(merchants__status=Merchant.Status.VERIFIED), distinct=True),
            riders_n=Count("riders", filter=Q(riders__status=Rider.Status.VERIFIED), distinct=True),
            agents_n=Count("agents", filter=Q(agents__status=Agent.Status.ACTIVE), distinct=True),
        )
        .order_by("-is_launch_area", "-members_n", "name")
    ):
        if a.members_n and a.merchants_n and a.agents_n:
            stage = "Live"
        elif a.members_n or a.merchants_n:
            stage = "Soft launch"
        else:
            stage = "Pilot" if a.is_launch_area else "Planned"
        rows.append({
            "area": a.name, "stage": stage, "members": a.members_n, "merchants": a.merchants_n,
            "riders": a.riders_n, "agents": a.agents_n, "launch": a.is_launch_area, "opened": short_date(a.created_at),
        })
    return rows


def supply_gaps(limit: int = 6) -> list[dict]:
    """Open member requests grouped by item+area, against the number of
    live offers that match the item — i.e. demand with no supply."""
    rows = (
        MemberRequest.objects.filter(status__in=[MemberRequest.Status.OPEN, MemberRequest.Status.RESPONDED])
        .values("item_name", "area__name")
        .annotate(requests=Count("id"))
        .order_by("-requests")[:limit * 2]
    )
    out = []
    for r in rows:
        matching = Offer.objects.filter(item_name__icontains=r["item_name"], area__name=r["area__name"])
        live = matching.filter(status=Offer.Status.ACTIVE, expires_at__gt=timezone.now()).count()
        last = matching.aggregate(m=Max("created_at"))["m"]
        out.append({
            "item": r["item_name"], "area": r["area__name"], "searches": r["requests"], "offers": live,
            "lastOffer": time_ago(last) if last else "Never",
        })
    out.sort(key=lambda g: (g["offers"], -g["searches"]))
    return out[:limit]


def price_movements(limit: int = 6) -> list[dict]:
    """Latest agent-collected price vs the one before it, per item+area."""
    by_key: dict[tuple, list[PriceRecord]] = defaultdict(list)
    for p in PriceRecord.objects.select_related("area").order_by("-created_at")[:500]:
        by_key[(p.item_name.lower(), p.area_id)].append(p)
    moves = []
    for (_item, _area), recs in by_key.items():
        if len(recs) < 2 or recs[0].price == recs[1].price:
            continue
        new, old = recs[0].price, recs[1].price
        change = pct_change(new, old)
        moves.append({
            "item": recs[0].item_name, "area": recs[0].area.name, "from": old, "to": new,
            "change": abs(change) if change is not None else 0, "direction": "up" if new > old else "down", "ts": recs[0].created_at,
        })
    moves.sort(key=lambda m: m["ts"], reverse=True)
    return moves[:limit]


# ---- admin list pages -------------------------------------------------------

PAGE_SIZE = 50


def paginate(request, items, size: int = PAGE_SIZE):
    from django.core.paginator import Paginator

    paginator = Paginator(items, size)
    return paginator.get_page(request.GET.get("page"))


def admin_members(params):
    now = timezone.now()
    qs = Member.objects.select_related("user", "area").annotate(
        saved=Coalesce(Sum("savings_records__saving_amount"), Value(ZERO), output_field=DecimalField()),
        claims_n=Count("claims", distinct=True),
        complaints_n=Count("complaints", distinct=True),
        referrals_n=Count("referrals", distinct=True),
    ).order_by("-created_at")
    q = (params.get("q") or "").strip()[:80]
    if q:
        qs = qs.filter(
            Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) | Q(user__phone__icontains=q) | Q(area__name__icontains=q)
        )
    area = params.get("area")
    if area and area.isdigit():
        qs = qs.filter(area_id=int(area))
    status = params.get("status")
    if status == "suspended":
        qs = qs.filter(Q(account_status=Member.AccountStatus.SUSPENDED) | Q(user__is_active=False))
    elif status == "active":
        qs = qs.filter(user__is_active=True, subscriptions__status=Subscription.Status.ACTIVE, subscriptions__current_period_end__gt=now).distinct()

    subs = {}
    return qs, subs


def admin_member_rows(page) -> list[dict]:
    member_ids = [m.pk for m in page]
    subs = {}
    for s in Subscription.objects.filter(member_id__in=member_ids).order_by("created_at"):
        subs[s.member_id] = s  # latest wins
    rows = []
    for m in page:
        sub = subs.get(m.pk)
        rows.append({
            "user_id": m.user_id,
            "name": display_name(m.user),
            "phone": m.user.phone,
            "area": m.area.name,
            "status": _status_label_for_member(m, sub),
            "renewal": short_date(sub.current_period_end) if sub and sub.current_period_end and sub.is_currently_active else "—",
            "saved": m.saved,
            "claims": m.claims_n,
            "complaints": m.complaints_n,
            "referrals": m.referrals_n,
            "last": time_ago(m.user.last_login) if m.user.last_login else "Never",
            "suspended": not m.user.is_active,
        })
    return rows


def admin_member_stats() -> dict:
    now = timezone.now()
    total = Member.objects.count()
    active = Subscription.objects.filter(status=Subscription.Status.ACTIVE, current_period_end__gt=now).values("member").distinct().count()
    suspended = Member.objects.filter(Q(account_status=Member.AccountStatus.SUSPENDED) | Q(user__is_active=False)).count()
    return {"total": total, "active": active, "expired": max(total - active - suspended, 0), "suspended": suspended}


def admin_subscriptions() -> dict:
    now = timezone.now()
    today = _day_start()
    plans = [
        {"code": p.code, "label": p.label, "price": p.price, "period": f"{p.period_days} days", "popular": p.is_popular, "active": p.is_active}
        for p in SubscriptionPlan.objects.order_by("price")
    ]
    stats = {
        "active": Subscription.objects.filter(status=Subscription.Status.ACTIVE, current_period_end__gt=now).count(),
        "due_today": Subscription.objects.filter(status=Subscription.Status.ACTIVE, current_period_end__gte=today, current_period_end__lt=today + timedelta(days=1)).count(),
        "failed": SubscriptionPayment.objects.filter(status=SubscriptionPayment.Status.FAILED, created_at__gte=now - timedelta(days=30)).count(),
        "pending": SubscriptionPayment.objects.filter(status=SubscriptionPayment.Status.PENDING).count(),
    }
    rows = []
    for sp in SubscriptionPayment.objects.select_related("subscription__member__user", "subscription__plan", "provider_payment").order_by("-created_at")[:100]:
        pp = getattr(sp, "provider_payment", None)
        rows.append({
            "member": display_name(sp.subscription.member.user),
            "plan": sp.subscription.plan.label,
            "paid": sp.amount,
            "method": pp.get_method_display() if pp else "—",
            "reference": str(pp.internal_reference)[:8].upper() if pp else str(sp.external_reference)[:8].upper(),
            "status": sp.get_status_display(),
            "renewal": short_date(sp.subscription.current_period_end) if sp.status == SubscriptionPayment.Status.SUCCESS and sp.subscription.current_period_end else "—",
        })
    return {"plans": plans, "stats": stats, "rows": rows}


def admin_merchants(params):
    qs = (
        Merchant.objects.select_related("user", "area", "category", "verified_by")
        .annotate(
            redemptions=Count("offers__claims", filter=Q(offers__claims__status=OfferClaim.Status.REDEEMED), distinct=True),
            total_claims=Count("offers__claims", distinct=True),
            expired_claims=Count("offers__claims", filter=Q(offers__claims__status=OfferClaim.Status.EXPIRED), distinct=True),
            sales=Coalesce(Sum("savings_records__member_price"), Value(ZERO), output_field=DecimalField()),
        )
        .order_by("-created_at")
    )
    q = (params.get("q") or "").strip()[:80]
    if q:
        qs = qs.filter(Q(business_name__icontains=q) | Q(area__name__icontains=q) | Q(category__label__icontains=q))
    status = params.get("status")
    if status in Merchant.Status.values:
        qs = qs.filter(status=status)
    return qs


def admin_merchant_rows(page) -> list[dict]:
    rows = []
    for m in page:
        denom = m.redemptions + m.expired_claims
        rows.append({
            "id": m.pk,
            "user_id": m.user_id,
            "name": m.business_name,
            "category": m.category.label,
            "area": m.area.name,
            "status": m.get_status_display(),
            "status_key": m.status,
            "redeem_rate": round(100 * m.redemptions / denom) if denom else None,
            "redemptions": m.redemptions,
            "sales": m.sales,
            "agent": display_name(m.verified_by) if m.verified_by else "—",
            "phone": m.phone or m.user.phone,
        })
    return rows


def admin_merchant_stats() -> dict:
    agg = Merchant.objects.aggregate(
        verified=Count("id", filter=Q(status=Merchant.Status.VERIFIED)),
        pending=Count("id", filter=Q(status=Merchant.Status.PENDING)),
        suspended=Count("id", filter=Q(status=Merchant.Status.SUSPENDED)),
    )
    agg["categories"] = OfferCategory.objects.filter(is_active=True).count()
    return agg


def admin_offers(params):
    qs = Offer.objects.select_related("merchant", "category", "area").order_by("-created_at")
    q = (params.get("q") or "").strip()[:80]
    if q:
        qs = qs.filter(Q(item_name__icontains=q) | Q(merchant__business_name__icontains=q) | Q(area__name__icontains=q))
    status = params.get("status")
    if status in Offer.Status.values:
        qs = qs.filter(status=status)
    return qs


def admin_offer_rows(page) -> list[dict]:
    return [
        {
            "id": o.pk, "item": o.item_name, "merchant": o.merchant.business_name, "category": o.category.label,
            "area": o.area.name, "normal": o.normal_price, "member": o.member_price, "stock": o.quantity,
            "expires": when_label(o.expires_at) if o.expires_at > timezone.now() else "Expired",
            "status": o.get_status_display(), "status_key": o.status,
        }
        for o in page
    ]


def admin_offer_stats() -> dict:
    now = timezone.now()
    return Offer.objects.aggregate(
        active=Count("id", filter=Q(status=Offer.Status.ACTIVE, expires_at__gt=now)),
        pending=Count("id", filter=Q(status=Offer.Status.PENDING)),
        paused=Count("id", filter=Q(status=Offer.Status.PAUSED)),
        reported=Count("id", filter=Q(status=Offer.Status.REPORTED)),
    )


def admin_claims(params):
    qs = OfferClaim.objects.select_related("offer__merchant", "member__user").order_by("-created_at")
    q = (params.get("q") or "").strip()[:80]
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(offer__item_name__icontains=q) | Q(offer__merchant__business_name__icontains=q))
    status = params.get("status")
    if status in OfferClaim.Status.values:
        qs = qs.filter(status=status)
    return qs


def admin_claim_rows(page) -> list[dict]:
    rows = []
    for c in page:
        status = c.status
        if status == OfferClaim.Status.CLAIMED and c.is_expired:
            status = OfferClaim.Status.EXPIRED
        suspicious = c.redemption_attempts >= 3
        rows.append({
            "code": c.code, "member": short_name(c.member.user), "merchant": c.offer.merchant.business_name,
            "item": c.offer.item_name, "saving": c.expected_saving,
            "expires": f"Used {clock_or_day(c.redeemed_at)}" if c.redeemed_at else when_label(c.expires_at) if status == OfferClaim.Status.CLAIMED else short_date(c.expires_at),
            "status": "Suspicious" if suspicious else dict(OfferClaim.Status.choices).get(status, status),
        })
    return rows


def admin_claim_stats() -> dict:
    now = timezone.now()
    today = _day_start()
    return {
        "active": OfferClaim.objects.filter(status=OfferClaim.Status.CLAIMED, expires_at__gt=now).count(),
        "used_today": OfferClaim.objects.filter(status=OfferClaim.Status.REDEEMED, redeemed_at__gte=today).count(),
        "refused": ClaimEvent.objects.filter(
            event_type__in=["redemption_locked_suspicious", "expired_on_redemption_attempt"], created_at__gte=today
        ).count(),
        "suspicious": OfferClaim.objects.filter(redemption_attempts__gte=3).count(),
    }


def admin_redemptions() -> dict:
    today = _day_start()
    thirty = timezone.now() - timedelta(days=30)
    redeemed = OfferClaim.objects.filter(status=OfferClaim.Status.REDEEMED)
    by_cat = [
        {"name": r["offer__category__label"], "value": r["n"]}
        for r in redeemed.filter(redeemed_at__gte=thirty).values("offer__category__label").annotate(n=Count("id")).order_by("-n")
    ]
    by_area = [
        {"name": r["offer__area__name"], "value": r["n"]}
        for r in redeemed.filter(redeemed_at__gte=thirty).values("offer__area__name").annotate(n=Count("id")).order_by("-n")[:8]
    ]
    reasons_raw = {
        "redemption_locked_suspicious": "Too many attempts (locked)",
        "expired_on_redemption_attempt": "Code expired",
    }
    reasons = [
        {"name": reasons_raw.get(r["event_type"], r["event_type"]), "value": r["n"]}
        for r in ClaimEvent.objects.filter(event_type__in=reasons_raw.keys(), created_at__gte=thirty).values("event_type").annotate(n=Count("id"))
    ]
    recent = [
        {
            "code": c.code, "member": short_name(c.member.user), "merchant": c.offer.merchant.business_name,
            "item": c.offer.item_name, "saving": c.expected_saving, "status": "Redeemed",
        }
        for c in redeemed.select_related("offer__merchant", "member__user").order_by("-redeemed_at")[:100]
    ]
    return {
        "stats": {
            "confirmed_today": redeemed.filter(redeemed_at__gte=today).count(),
            "refused_today": ClaimEvent.objects.filter(
                event_type__in=list(reasons_raw), created_at__gte=today
            ).count(),
            "top_area": by_area[0]["name"] if by_area else "—",
            "top_category": by_cat[0]["name"] if by_cat else "—",
        },
        "by_category": by_cat, "by_area": by_area, "reasons": reasons, "recent": recent,
    }


def admin_riders(params):
    qs = (
        Rider.objects.select_related("user", "area")
        .annotate(
            jobs_n=Count("delivery_jobs", filter=Q(delivery_jobs__status=DeliveryJob.Status.DELIVERED), distinct=True),
            failed_n=Count("delivery_jobs", filter=Q(delivery_jobs__status=DeliveryJob.Status.FAILED), distinct=True),
            commission=Coalesce(Sum("earnings__commission_amount"), Value(ZERO), output_field=DecimalField()),
            gross=Coalesce(Sum("earnings__gross_amount"), Value(ZERO), output_field=DecimalField()),
        )
        .order_by("-created_at")
    )
    q = (params.get("q") or "").strip()[:80]
    if q:
        qs = qs.filter(Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) | Q(user__phone__icontains=q) | Q(area__name__icontains=q) | Q(plate_number__icontains=q))
    status = params.get("status")
    if status in Rider.Status.values:
        qs = qs.filter(status=status)
    return qs


def admin_rider_rows(page) -> list[dict]:
    return [
        {
            "id": r.pk, "user_id": r.user_id, "suspended": not r.user.is_active,
            "name": display_name(r.user), "phone": r.user.phone, "area": r.area.name,
            "vehicle": r.get_vehicle_type_display(), "plate": r.plate_number or "—",
            "status": r.get_status_display(), "status_key": r.status, "available": r.is_available,
            "jobs": r.jobs_n, "failed": r.failed_n, "commission": r.commission, "gross": r.gross,
        }
        for r in page
    ]


def admin_rider_stats() -> dict:
    return Rider.objects.aggregate(
        verified=Count("id", filter=Q(status=Rider.Status.VERIFIED)),
        pending=Count("id", filter=Q(status=Rider.Status.PENDING)),
        available=Count("id", filter=Q(status=Rider.Status.VERIFIED, is_available=True)),
        suspended=Count("id", filter=Q(status=Rider.Status.SUSPENDED)),
    )


def admin_routes() -> dict:
    routes = []
    qs = (
        SharedRoute.objects.select_related("rider__user", "origin_area", "destination_area")
        .annotate(pkg=Count("packages", distinct=True))
        .order_by("-departure_time")[:100]
    )
    totals = {"packages": 0, "gross": ZERO, "commission": ZERO}
    for r in qs:
        e = RiderEarning.objects.filter(delivery_job__route=r).aggregate(g=Sum("gross_amount"), c=Sum("commission_amount"))
        gross, comm = e["g"] or ZERO, e["c"] or ZERO
        routes.append({
            "id": r.pk, "name": f"{r.origin_area.name} → {r.destination_area.name}", "dispatch": when_label(r.departure_time) if r.departure_time > timezone.now() else short_date(r.departure_time),
            "rider": display_name(r.rider.user), "packages": r.pkg, "max": r.max_packages, "earnings": gross, "commission": comm,
            "status": r.get_status_display(),
        })
        totals["packages"] += r.pkg
        totals["gross"] += gross
        totals["commission"] += comm
    return {"routes": routes, "totals": totals}


def admin_agents() -> dict:
    rows = []
    for a in Agent.objects.select_related("user").prefetch_related("areas").order_by("-created_at"):
        suspended = a.status == Agent.Status.SUSPENDED or not a.user.is_active
        earned = AgentEarning.objects.filter(agent=a).aggregate(t=Sum("amount"))["t"] or ZERO
        rows.append({
            "user_id": a.user_id,
            "name": display_name(a.user),
            "phone": a.user.phone,
            "areas": [x.name for x in a.areas.all()],
            "status": "Suspended" if suspended else "Active",
            "merchants": Merchant.objects.filter(verified_by=a.user, status=Merchant.Status.VERIFIED).count(),
            "riders": Rider.objects.filter(verified_by=a.user, status=Rider.Status.VERIFIED).count(),
            "prices": PriceRecord.objects.filter(agent=a).count(),
            "complaints": Complaint.objects.filter(assigned_agent=a).count(),
            "earnings": earned,
            "last": time_ago(a.user.last_login) if a.user.last_login else "Never",
            "suspended": suspended,
        })
    active_areas = Area.objects.filter(is_active=True).count()
    covered = Area.objects.filter(is_active=True, agents__status=Agent.Status.ACTIVE).distinct().count()
    top = max(rows, key=lambda r: r["merchants"] + r["riders"] + r["prices"], default=None)
    stats = {
        "total": len(rows),
        "active": sum(1 for r in rows if r["status"] == "Active"),
        "suspended": sum(1 for r in rows if r["status"] == "Suspended"),
        "covered": covered, "areas": active_areas, "covered_label": f"{covered} / {active_areas}",
        "earnings_total": sum((r["earnings"] for r in rows), ZERO),
        "top": top["name"] if top and (top["merchants"] + top["riders"] + top["prices"]) else "—",
    }
    return {"rows": rows, "stats": stats, "areas": areas_active()}


def admin_prices() -> dict:
    by_key: dict[tuple, list[PriceRecord]] = defaultdict(list)
    for p in PriceRecord.objects.select_related("area", "agent__user").order_by("-created_at")[:1000]:
        by_key[(p.item_name.lower(), p.area_id)].append(p)
    rows = []
    for recs in by_key.values():
        cur = recs[0]
        prev = recs[1].price if len(recs) > 1 else cur.price
        window = [r.price for r in recs[:20]]
        rows.append({
            "item": cur.item_name, "area": cur.area.name, "current": cur.price, "previous": prev, "diff": cur.price - prev,
            "low": min(window), "high": max(window), "agent": display_name(cur.agent.user), "date": time_ago(cur.created_at),
            "ts": cur.created_at,
        })
    rows.sort(key=lambda r: r["ts"], reverse=True)
    week = timezone.now() - timedelta(days=7)
    stats = {
        "items": len({k[0] for k in by_key}),
        "areas_today": PriceRecord.objects.filter(created_at__gte=_day_start()).values("area").distinct().count(),
        "areas_total": Area.objects.filter(is_active=True).count(),
        "drops": sum(1 for r in rows if r["diff"] < 0 and r["ts"] >= week),
    }
    return {"rows": rows[:200], "stats": stats}


def admin_payments() -> dict:
    now = timezone.now()
    today = _day_start()
    month = _month_start()
    ok = Payment.objects.filter(status=Payment.Status.SUCCESS)
    stats = {
        "today": ok.filter(created_at__gte=today).aggregate(t=Sum("amount"))["t"] or ZERO,
        "success": ok.count(),
        "failed": Payment.objects.filter(status=Payment.Status.FAILED).count(),
        "review": Payment.objects.filter(status=Payment.Status.REQUIRES_REVIEW).count(),
        "month": ok.filter(created_at__gte=month).aggregate(t=Sum("amount"))["t"] or ZERO,
    }
    rows = [
        {
            "ref": str(p.internal_reference)[:8].upper(), "who": display_name(p.user), "type": p.get_purpose_display(),
            "amount": p.amount, "method": p.get_method_display(), "status": p.get_status_display(), "time": time_ago(p.created_at),
        }
        for p in Payment.objects.select_related("user").order_by("-created_at")[:100]
    ]
    withdrawals = [
        {
            "ref": str(w.internal_reference)[:8].upper(), "who": display_name(w.user), "amount": w.amount, "fee": w.fee,
            "net": w.net_amount, "status": w.get_status_display(), "time": time_ago(w.created_at),
        }
        for w in Withdrawal.objects.select_related("user").order_by("-created_at")[:50]
    ]
    return {"stats": stats, "rows": rows, "withdrawals": withdrawals, "wallet": ioTec_wallet()}


def ioTec_wallet() -> dict:
    """Balance of the ioTec Pay wallet (cached 60s so the page never hammers the API).
    Never raises: the page must render even if ioTec is unreachable."""
    from django.core.cache import cache

    from payments import config

    if not config.is_configured():
        return {"state": "not_configured"}
    cached = cache.get("iotec:wallet_view")
    if cached:
        return cached
    try:
        from payments.services.iotec_disbursements import get_wallet_balance

        w = get_wallet_balance()
        view = {"state": "ok", "name": w.get("name") or "ioTec wallet", "balance": w.get("actualBalance"),
                "currency": w.get("currency") or config.currency()}
        cache.set("iotec:wallet_view", view, 60)
        return view
    except Exception:
        return {"state": "unavailable"}


def admin_settlements() -> dict:
    """Derived (there is no Settlement table): what each rider has earned,
    withdrawn and can still withdraw, plus what each agent has earned."""
    rows = []
    totals = {"pending": ZERO, "paid": ZERO, "commission": ZERO, "agent_earned": ZERO}
    for r in Rider.objects.select_related("user").annotate(
        gross=Coalesce(Sum("earnings__gross_amount"), Value(ZERO), output_field=DecimalField()),
        commission=Coalesce(Sum("earnings__commission_amount"), Value(ZERO), output_field=DecimalField()),
        net=Coalesce(Sum("earnings__net_amount"), Value(ZERO), output_field=DecimalField()),
    ).filter(earnings__isnull=False).distinct():
        paid = Withdrawal.objects.filter(user=r.user, status=Withdrawal.Status.COMPLETED).aggregate(t=Sum("amount"))["t"] or ZERO
        inflight = Withdrawal.objects.filter(
            user=r.user, status__in=[Withdrawal.Status.PENDING, Withdrawal.Status.PROCESSING]
        ).aggregate(t=Sum("amount"))["t"] or ZERO
        pending = r.net - paid - inflight
        rows.append({
            "who": display_name(r.user), "type": "Rider earnings", "gross": r.gross, "commission": r.commission,
            "net": r.net, "paid": paid, "pending": max(pending, ZERO), "inflight": inflight,
        })
        totals["pending"] += max(pending, ZERO)
        totals["paid"] += paid
        totals["commission"] += r.commission
    for a in Agent.objects.select_related("user"):
        earned = AgentEarning.objects.filter(agent=a).aggregate(t=Sum("amount"))["t"] or ZERO
        if earned:
            rows.append({
                "who": display_name(a.user), "type": "Agent earnings", "gross": earned, "commission": ZERO,
                "net": earned, "paid": None, "pending": None, "inflight": ZERO,
            })
            totals["agent_earned"] += earned
    return {"rows": rows, "totals": totals}


def admin_complaints(params):
    qs = Complaint.objects.select_related("member__user", "area", "assigned_agent__user").order_by("-created_at")
    q = (params.get("q") or "").strip()[:80]
    if q:
        qs = qs.filter(Q(subject__icontains=q) | Q(description__icontains=q) | Q(area__name__icontains=q))
    status = params.get("status")
    if status in Complaint.Status.values:
        qs = qs.filter(status=status)
    return qs


def admin_complaint_rows(page) -> list[dict]:
    now = timezone.now()
    rows = []
    for c in page:
        age = now - c.created_at
        closed = c.status in (Complaint.Status.RESOLVED, Complaint.Status.REJECTED)
        rows.append({
            "id": c.pk, "ref": f"CMP-{c.pk}", "member": short_name(c.member.user), "subject": c.subject, "area": c.area.name,
            "agent": display_name(c.assigned_agent.user) if c.assigned_agent_id else "Unassigned",
            "age": time_ago(c.created_at), "overdue": (not closed) and age > timedelta(hours=72),
            "status": c.get_status_display(), "status_key": c.status, "closed": closed,
        })
    return rows


def admin_complaint_stats() -> dict:
    now = timezone.now()
    week = now - timedelta(days=7)
    return {
        "open": Complaint.objects.filter(status__in=[Complaint.Status.OPEN, Complaint.Status.INVESTIGATING]).count(),
        "overdue": Complaint.objects.filter(
            status__in=[Complaint.Status.OPEN, Complaint.Status.INVESTIGATING], created_at__lte=now - timedelta(hours=72)
        ).count(),
        "resolved_week": Complaint.objects.filter(status=Complaint.Status.RESOLVED, updated_at__gte=week).count(),
        "escalated": Complaint.objects.filter(status=Complaint.Status.ESCALATED).count(),
    }


def admin_notifications() -> dict:
    today = _day_start()
    by_cat = [
        {"name": dict(Notification._meta.get_field("category").choices).get(r["category"], r["category"]), "value": r["n"]}
        for r in Notification.objects.filter(created_at__gte=today - timedelta(days=30)).values("category").annotate(n=Count("id")).order_by("-n")
    ]
    recent = [
        {"who": display_name(n.user), "title": n.title, "category": n.get_category_display(), "read": n.is_read, "when": time_ago(n.created_at)}
        for n in Notification.objects.select_related("user").order_by("-created_at")[:50]
    ]
    return {
        "stats": {
            "today": Notification.objects.filter(created_at__gte=today).count(),
            "unread": Notification.objects.filter(is_read=False).count(),
            "month": Notification.objects.filter(created_at__gte=_month_start()).count(),
        },
        "by_category": by_cat, "recent": recent, "areas": areas_active(),
    }


def admin_reports() -> dict:
    ov = admin_overview()
    month = _month_start()
    subs_month = SubscriptionPayment.objects.filter(status=SubscriptionPayment.Status.SUCCESS, created_at__gte=month).aggregate(t=Sum("amount"))["t"] or ZERO
    confirmed_month = SavingsRecord.objects.filter(created_at__gte=month).aggregate(t=Sum("saving_amount"))["t"] or ZERO
    return {
        "charts": ov["charts"],
        "stats": {
            "confirmed_month": confirmed_month,
            "subs_month": subs_month,
            "net_benefit": confirmed_month - subs_month,
            "payment_success_rate": _payment_success_rate(),
        },
        "month_label": timezone.localtime().strftime("%B %Y"),
    }


def _payment_success_rate():
    total = Payment.objects.exclude(status__in=[Payment.Status.CREATED, Payment.Status.PENDING, Payment.Status.SENT_TO_VENDOR]).count()
    if not total:
        return None
    return round(100 * Payment.objects.filter(status=Payment.Status.SUCCESS).count() / total)


def admin_settings() -> dict:
    from core.models import SystemSetting

    return {
        "plans": [
            {"id": p.pk, "code": p.code, "label": p.label, "price": p.price, "period": f"{p.period_days} days", "active": p.is_active}
            for p in SubscriptionPlan.objects.order_by("price")
        ],
        "areas": list(Area.objects.order_by("name")),
        "settings": list(SystemSetting.objects.order_by("key")),
        "categories": list(OfferCategory.objects.order_by("label")),
        "packages": list(PromotionPackage.objects.order_by("price")),
    }


def admin_pickup() -> dict:
    return {
        "points": list(PickupPoint.objects.select_related("area")),
        "areas": areas_active(),
        "stats": {
            "total": PickupPoint.objects.count(),
            "active": PickupPoint.objects.filter(is_active=True).count(),
            "areas": PickupPoint.objects.filter(is_active=True).values("area").distinct().count(),
        },
    }


def admin_tasks() -> dict:
    now = timezone.now()
    tasks = AgentTask.objects.select_related("agent__user", "area").order_by("status", "due_at", "-created_at")[:100]
    rows = [
        {"id": t.pk, "title": t.title, "kind": t.get_kind_display(), "agent": display_name(t.agent.user),
         "area": t.area.name if t.area else "—", "due": when_label(t.due_at) if t.due_at else "—",
         "status": t.get_status_display(), "status_key": t.status,
         "overdue": bool(t.status == AgentTask.Status.OPEN and t.due_at and t.due_at < now)}
        for t in tasks
    ]
    return {
        "rows": rows,
        "agents": [{"id": a.pk, "name": display_name(a.user)} for a in Agent.objects.filter(status=Agent.Status.ACTIVE).select_related("user")],
        "areas": areas_active(),
        "stats": {
            "open": AgentTask.objects.filter(status=AgentTask.Status.OPEN).count(),
            "overdue": AgentTask.objects.filter(status=AgentTask.Status.OPEN, due_at__lt=now).count(),
            "done_week": AgentTask.objects.filter(status=AgentTask.Status.DONE, completed_at__gte=now - timedelta(days=7)).count(),
        },
        "kinds": AgentTask.Kind.choices,
    }


def notifications_for(user, limit: int = 50) -> dict:
    qs = Notification.objects.filter(user=user).order_by("-created_at")
    return {
        "items": [
            {"id": n.pk, "title": n.title, "message": n.message, "category": n.get_category_display(),
             "read": n.is_read, "when": time_ago(n.created_at)}
            for n in qs[:limit]
        ],
        "unread": qs.filter(is_read=False).count(),
    }
