"""Hub pages. Every page is rendered from the database via ``hub.selectors``.

Per-user pages (member / merchant / rider / agent) are always scoped from
``request.user`` — nothing in the URL decides whose data is shown. Writes are
done by the JSON API under /api/v1/ (see static/hub/js/api.js).
"""
from copy import deepcopy

from django.shortcuts import render

from accounts.decorators import admin_required, role_required
from . import selectors as s
from .nav import ALL_ROLES, ROLE_CONFIG


def _is_active(item, role_key, current_url_name):
    if item["url"] != current_url_name:
        return False
    if role_key == "admin":
        return True
    return bool(item.get("exact"))


def _switchable_roles(user):
    """Only offer role pills for roles this user actually holds."""
    held = user.role_names()
    out = []
    for r in ALL_ROLES:
        if user.is_superuser or r["role"] in held or (r["role"] == "admin" and user.is_admin()):
            out.append(dict(r))
    return out


def dashboard_context(request, role_key, current_url_name, extra=None, meta=""):
    """Shared layout context. The signed-in user's real name replaces the
    placeholder identity that used to be hard-coded in nav.py."""
    cfg = deepcopy(ROLE_CONFIG[role_key])
    cfg["user"] = {"name": s.display_name(request.user), "meta": meta or cfg["user"]["meta"]}
    ctx = {
        "role_key": role_key,
        "cfg": cfg,
        "nav": [dict(i, active=_is_active(i, role_key, current_url_name)) for i in cfg["nav"]],
        "bottom_nav": [dict(i, active=_is_active(i, role_key, current_url_name)) for i in cfg["bottom_nav"]],
        "all_roles": _switchable_roles(request.user),
    }
    if extra:
        ctx.update(extra)
    return ctx


def _no_profile(request, role_key, url_name, label):
    ctx = dashboard_context(request, role_key, url_name, {"missing_label": label}, meta="Profile not set up")
    return render(request, "hub/no_profile.html", ctx, status=200)


def _page(request, template, role_key, url_name, data, meta=""):
    return render(request, template, dashboard_context(request, role_key, url_name, data, meta=meta))


# ---------------------------------------------------------------- Landing --

def landing(request):
    return render(request, "hub/landing.html", s.landing_context())


# ----------------------------------------------------------------- Member --

@role_required("member")
def member(request):
    data = s.member_context(request.user, request.GET)
    if data is None:
        return _no_profile(request, "member", "member", "member")
    return _page(request, "hub/member.html", "member", "member", data, meta=f"Member · {data['member'].area.name}")


# --------------------------------------------------------------- Merchant --

@role_required("merchant")
def merchant(request):
    data = s.merchant_context(request.user)
    if data is None:
        return _no_profile(request, "merchant", "merchant", "merchant")
    m = data["merchant"]
    return _page(request, "hub/merchant.html", "merchant", "merchant", data,
                 meta=f"{m.get_status_display()} · {m.category.label}")


# ------------------------------------------------------------------ Rider --

@role_required("rider")
def rider(request):
    data = s.rider_context(request.user)
    if data is None:
        return _no_profile(request, "rider", "rider", "rider")
    r = data["rider"]
    return _page(request, "hub/rider.html", "rider", "rider", data,
                 meta=f"{r.get_status_display()} · {r.area.name}")


# ------------------------------------------------------------------ Agent --

@role_required("agent")
def agent(request):
    data = s.agent_context(request.user)
    if data is None:
        return _no_profile(request, "agent", "agent", "agent")
    names = " / ".join(a.name for a in data["areas"]) or "No areas assigned"
    return _page(request, "hub/agent.html", "agent", "agent", data, meta=f"Area · {names}")


# ------------------------------------------------------------------ Admin --

def _admin(request, template, url_name, data):
    return _page(request, template, "admin", url_name, data, meta="Platform admin")


@admin_required
def admin_index(request):
    return _admin(request, "hub/admin/index.html", "admin_index", s.admin_overview())


@admin_required
def admin_members(request):
    qs, _ = s.admin_members(request.GET)
    page = s.paginate(request, qs)
    return _admin(request, "hub/admin/members.html", "admin_members", {
        "page": page, "rows": s.admin_member_rows(page), "stats": s.admin_member_stats(),
        "filters": {"q": request.GET.get("q", ""), "status": request.GET.get("status", "")},
    })


@admin_required
def admin_subscriptions(request):
    return _admin(request, "hub/admin/subscriptions.html", "admin_subscriptions", s.admin_subscriptions())


@admin_required
def admin_merchants(request):
    page = s.paginate(request, s.admin_merchants(request.GET))
    return _admin(request, "hub/admin/merchants.html", "admin_merchants", {
        "page": page, "rows": s.admin_merchant_rows(page), "stats": s.admin_merchant_stats(),
        "filters": {"q": request.GET.get("q", ""), "status": request.GET.get("status", "")},
    })


@admin_required
def admin_offers(request):
    page = s.paginate(request, s.admin_offers(request.GET))
    return _admin(request, "hub/admin/offers.html", "admin_offers", {
        "page": page, "rows": s.admin_offer_rows(page), "stats": s.admin_offer_stats(),
        "filters": {"q": request.GET.get("q", ""), "status": request.GET.get("status", "")},
    })


@admin_required
def admin_claims(request):
    page = s.paginate(request, s.admin_claims(request.GET))
    return _admin(request, "hub/admin/claims.html", "admin_claims", {
        "page": page, "rows": s.admin_claim_rows(page), "stats": s.admin_claim_stats(),
        "filters": {"q": request.GET.get("q", ""), "status": request.GET.get("status", "")},
    })


@admin_required
def admin_redemptions(request):
    return _admin(request, "hub/admin/redemptions.html", "admin_redemptions", s.admin_redemptions())


@admin_required
def admin_riders(request):
    page = s.paginate(request, s.admin_riders(request.GET))
    return _admin(request, "hub/admin/riders.html", "admin_riders", {
        "page": page, "rows": s.admin_rider_rows(page), "stats": s.admin_rider_stats(),
        "filters": {"q": request.GET.get("q", ""), "status": request.GET.get("status", "")},
    })


@admin_required
def admin_routes(request):
    return _admin(request, "hub/admin/routes.html", "admin_routes", s.admin_routes())


@admin_required
def admin_pickup(request):
    return _admin(request, "hub/admin/pickup.html", "admin_pickup", s.admin_pickup())


@admin_required
def admin_agents(request):
    return _admin(request, "hub/admin/agents.html", "admin_agents", s.admin_agents())


@admin_required
def admin_tasks(request):
    return _admin(request, "hub/admin/tasks.html", "admin_tasks", s.admin_tasks())


@admin_required
def admin_prices(request):
    return _admin(request, "hub/admin/prices.html", "admin_prices", s.admin_prices())


@admin_required
def admin_payments(request):
    return _admin(request, "hub/admin/payments.html", "admin_payments", s.admin_payments())


@admin_required
def admin_settlements(request):
    return _admin(request, "hub/admin/settlements.html", "admin_settlements", s.admin_settlements())


@admin_required
def admin_complaints(request):
    page = s.paginate(request, s.admin_complaints(request.GET))
    return _admin(request, "hub/admin/complaints.html", "admin_complaints", {
        "page": page, "rows": s.admin_complaint_rows(page), "stats": s.admin_complaint_stats(),
        "filters": {"q": request.GET.get("q", ""), "status": request.GET.get("status", "")},
    })


@admin_required
def admin_notifications(request):
    return _admin(request, "hub/admin/notifications.html", "admin_notifications", s.admin_notifications())


@admin_required
def admin_reports(request):
    return _admin(request, "hub/admin/reports.html", "admin_reports", s.admin_reports())


@admin_required
def admin_settings(request):
    return _admin(request, "hub/admin/settings.html", "admin_settings", s.admin_settings())


# ------------------------------------------------------- signed-in extras --
from django.contrib.auth.decorators import login_required  # noqa: E402


@login_required
def notifications_page(request):
    role = request.user.role if request.user.role in ROLE_CONFIG else "member"
    data = s.notifications_for(request.user)
    return render(request, "hub/notifications.html", dashboard_context(request, role, "notifications", data))


@login_required
def apply_merchant(request):
    from merchants.models import Merchant
    from offers.models import OfferCategory
    from core.models import Area

    existing = Merchant.objects.filter(user=request.user).first()
    role = request.user.role if request.user.role in ROLE_CONFIG else "member"
    return render(request, "hub/apply_merchant.html", dashboard_context(request, role, "apply_merchant", {
        "existing": existing, "categories": OfferCategory.objects.filter(is_active=True), "areas": Area.objects.filter(is_active=True),
    }))


@login_required
def apply_rider(request):
    from riders.models import Rider
    from core.models import Area

    existing = Rider.objects.filter(user=request.user).prefetch_related("documents").first()
    role = request.user.role if request.user.role in ROLE_CONFIG else "member"
    return render(request, "hub/apply_rider.html", dashboard_context(request, role, "apply_rider", {
        "existing": existing, "areas": Area.objects.filter(is_active=True),
        "vehicle_types": Rider.VehicleType.choices, "doc_types": __import__("riders.models", fromlist=["RiderDocument"]).RiderDocument.DocType.choices,
    }))


@login_required
def payment_return(request):
    """Where a cardholder lands after PegPay. We never trust the query string ioTec appends (anyone can
    type a URL): we only use OUR reference, check the payment belongs to this user, and let the page ask
    the server — which asks ioTec — what really happened."""
    from django.core.exceptions import ValidationError
    from django.http import Http404

    from payments.models import Payment

    ref = request.GET.get("ref", "")
    try:
        payment = Payment.objects.get(internal_reference=ref, user=request.user)
    except (Payment.DoesNotExist, ValidationError, ValueError):
        raise Http404("Payment not found")
    role = request.user.role if request.user.role in ROLE_CONFIG else "member"
    back = "merchant" if payment.purpose == Payment.Purpose.PROMOTION else "member"
    return render(request, "hub/payment_return.html", dashboard_context(
        request, role, "payment_return", {"payment": payment, "back_url_name": back}))
