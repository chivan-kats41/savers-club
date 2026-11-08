"""Give super admins every profile on the platform.

A super admin can already *open* the member / merchant / rider / agent pages (``User.has_role`` is always true for
them) but those pages need a profile row to show anything. This module creates the missing rows so a super admin
can test and operate every part of the site with one login.

Rules (all enforced + tested):
  * Only super admins: ``is_superuser`` or role ``super_admin``. Regular ``admin`` staff are NOT given merchant /
    rider / agent identities (that would be a privilege they were not granted).
  * Idempotent and non-destructive: an existing profile is never modified (a suspended merchant stays suspended).
  * The agent profile covers EVERY active area, and new areas are added the next time this runs (login / first visit).
  * Merchant and rider profiles are marked verified, with a real audit record saying why.
  * Never depends on seed data: if no area / offer category exists yet, a default one is created (a super admin must
    always end up with all four profiles). Each profile is created independently, so one failure never blocks the others.
  * Never raises into the caller: user creation and login must not fail because a profile couldn't be made.
    A profile that still can't be created is reported with the reason instead.
"""
import logging
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from .models import Role, UserRole

logger = logging.getLogger("security")

PROFILES = ("member", "merchant", "rider", "agent")


def is_super_admin(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_superuser or user.role == Role.SUPER_ADMIN))


@dataclass
class Report:
    created: list = field(default_factory=list)      # profiles created in this run
    present: set = field(default_factory=set)        # profiles that exist after this run
    skipped: dict = field(default_factory=dict)      # profile -> human-readable reason it could not be created
    areas_added: int = 0                             # areas newly added to the agent profile

    @property
    def changed(self) -> bool:
        return bool(self.created or self.areas_added)


def _display(user) -> str:
    name = user.get_full_name().strip() if hasattr(user, "get_full_name") else ""
    return name or user.phone


def _pick_area(Area):
    """Best existing area (launch areas first, active before inactive); creates a default one only if NONE exist."""
    area = (Area.objects.filter(is_active=True, is_launch_area=True).order_by("name").first()
            or Area.objects.filter(is_active=True).order_by("name").first()
            or Area.objects.order_by("pk").first())
    if area is None:
        area = Area.objects.create(name="Default Area", is_launch_area=False)
        logger.info("No areas existed: created 'Default Area' for the super admin's profiles.")
    return area


def _pick_category(OfferCategory):
    """Best existing offer category ('general' first, active before inactive); creates 'General Shop' only if NONE exist."""
    cat = (OfferCategory.objects.filter(is_active=True, key="general").first()
           or OfferCategory.objects.filter(is_active=True).order_by("label").first()
           or OfferCategory.objects.order_by("pk").first())
    if cat is None:
        cat = OfferCategory.objects.create(key="general", label="General Shop", emoji="\U0001F3EA")
        logger.info("No offer categories existed: created 'General Shop' for the super admin's merchant profile.")
    return cat


def ensure_admin_profiles(user) -> Report:
    report = Report()
    if not is_super_admin(user):
        return report
    try:
        _ensure(user, report)
    except Exception:  # never break signup/login over this
        logger.exception("Could not ensure admin profiles for user=%s", user.pk)
    return report


def _step(user, report: Report, name: str, fn):
    """Run one profile's creation on its own savepoint so a failure here can't undo or block the others."""
    try:
        with transaction.atomic():
            fn()
    except Exception as exc:
        logger.exception("Could not create the %s profile for super admin %s", name, user.pk)
        report.skipped[name] = f"Unexpected error ({type(exc).__name__}). Details are in the server log."


def _ensure(user, report: Report):
    # Imported here: these apps import accounts, so top-level imports would be circular.
    from agents.models import Agent
    from core.models import Area
    from members.models import Member
    from merchants.models import Merchant, MerchantVerification
    from offers.models import OfferCategory
    from riders.models import Rider, RiderVerification

    now = timezone.now()
    ctx = {}

    def area():
        if "area" not in ctx:
            ctx["area"] = _pick_area(Area)
        return ctx["area"]

    def make_member():
        Member.objects.create(user=user, area=area())
        report.created.append("member")

    def make_merchant():
        merchant = Merchant.objects.create(
            user=user, business_name=f"{_display(user)} (Admin)"[:150], category=_pick_category(OfferCategory),
            area=area(), vendor_type="Platform admin account", phone=user.phone, status=Merchant.Status.VERIFIED,
            verified_by=user, verified_at=now,
        )
        MerchantVerification.objects.create(
            merchant=merchant, performed_by=user, outcome=Merchant.Status.VERIFIED,
            checklist={"auto_created_for_super_admin": True},
            notes="Created automatically because this account is a super admin.",
        )
        report.created.append("merchant")

    def make_rider():
        rider = Rider.objects.create(
            user=user, area=area(), vehicle_type=Rider.VehicleType.BODA, status=Rider.Status.VERIFIED,
            verified_by=user, verified_at=now,
            is_available=False,   # an admin test rider shouldn't show up as an available boda for real jobs
        )
        RiderVerification.objects.create(
            rider=rider, performed_by=user, outcome=Rider.Status.VERIFIED,
            checklist={"auto_created_for_super_admin": True},
            notes="Created automatically because this account is a super admin.",
        )
        report.created.append("rider")

    def make_agent():
        Agent.objects.create(user=user, status=Agent.Status.ACTIVE)
        report.created.append("agent")

    for name, model, make in (("member", Member, make_member), ("merchant", Merchant, make_merchant),
                              ("rider", Rider, make_rider), ("agent", Agent, make_agent)):
        if not model.objects.filter(user=user).exists():
            _step(user, report, name, make)
        if model.objects.filter(user=user).exists():
            report.present.add(name)
            report.skipped.pop(name, None)

    # --- agent covers every active area (including areas created since last time) ----------------------------
    agent = Agent.objects.filter(user=user).first()
    if agent is not None:
        missing_ids = list(Area.objects.filter(is_active=True).exclude(pk__in=agent.areas.values_list("pk", flat=True))
                           .values_list("pk", flat=True))
        if missing_ids:
            agent.areas.add(*missing_ids)
            report.areas_added = len(missing_ids)

    # --- role switcher rows: every role this super admin may switch into ------------------------------------
    for role in (Role.MEMBER, Role.MERCHANT, Role.RIDER, Role.AGENT):
        UserRole.objects.update_or_create(user=user, role=role, defaults={"is_active": True})

    if report.changed:
        logger.info("Admin profiles ensured user=%s created=%s areas_added=%s skipped=%s",
                    user.pk, report.created, report.areas_added, list(report.skipped))
