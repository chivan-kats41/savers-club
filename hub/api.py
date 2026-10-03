"""Extra JSON endpoints used by the hub pages: onboarding, uploads, interaction
tracking, notifications and the admin controls. Everything here follows the
same envelope as the rest of the API: {"success": bool, "data"|"error": ...}.
"""
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.models import Role, User, UserRole
from accounts.permissions import HasCapability, IsRole
from agents.models import Agent, AgentTask
from core.middleware import get_client_ip
from core.models import Area, AuditLog, SystemSetting
from core.uploads import clean_document, clean_image
from deliveries.models import PickupPoint
from merchants.models import Merchant, MerchantVerification
from notifications.models import Notification, NotificationCategory
from notifications.services.dispatch import notify
from offers.models import Offer, OfferCategory, OfferImage, OfferInteraction
from riders.models import Rider, RiderDocument, RiderVerification
from subscriptions.models import SubscriptionPlan

logger = logging.getLogger("hub")

IsMember = IsRole.for_roles("member")
IsMerchant = IsRole.for_roles("merchant")
IsRider = IsRole.for_roles("rider")
IsAgent = IsRole.for_roles("agent")

PARSERS = [JSONParser, FormParser, MultiPartParser]


def ok(data=None, status=200):
    return Response({"success": True, "data": data if data is not None else {}}, status=status)


def fail(code, message, status=400):
    return Response({"success": False, "error": {"code": code, "message": message, "details": {}}}, status=status)


def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_decimal(value):
    try:
        d = Decimal(str(value))
        return d if d.is_finite() else None
    except (InvalidOperation, TypeError):
        return None


def audit(request, action, obj, **meta):
    AuditLog.objects.create(
        actor=request.user, action=action, object_type=type(obj).__name__, object_id=str(obj.pk),
        ip_address=get_client_ip(request), metadata=meta or {},
    )


class Throttled(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"
    parser_classes = PARSERS


# ------------------------------------------------------------- onboarding --

def _grant_role(user, role):
    UserRole.objects.update_or_create(user=user, role=role, defaults={"is_active": True})


class MerchantApplyView(Throttled):
    """POST /api/v1/merchant/apply/ — any signed-in user can apply; the account
    stays PENDING (cannot post offers) until an agent verifies the business."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        d = request.data
        if Merchant.objects.filter(user=request.user).exists():
            return fail("ALREADY_APPLIED", "You already have a merchant application.", 409)
        name = str(d.get("business_name", "")).strip()[:150]
        category = OfferCategory.objects.filter(pk=to_int(d.get("category")), is_active=True).first()
        area = Area.objects.filter(pk=to_int(d.get("area")), is_active=True).first()
        if len(name) < 2 or category is None or area is None:
            return fail("INVALID", "Business name, category and area are required.")
        merchant = Merchant.objects.create(
            user=request.user, business_name=name, category=category, area=area,
            vendor_type=str(d.get("vendor_type", ""))[:100], address=str(d.get("address", ""))[:255],
            phone=str(d.get("phone") or request.user.phone)[:20], whatsapp=str(d.get("whatsapp", ""))[:20],
            status=Merchant.Status.PENDING,
        )
        _grant_role(request.user, Role.MERCHANT)
        notify(request.user, NotificationCategory.REGISTRATION, "Application received",
               "An area agent will visit to verify your business. You'll be notified when it's approved.")
        return ok({"id": merchant.pk, "status": merchant.status}, 201)


class RiderApplyView(Throttled):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        d = request.data
        if Rider.objects.filter(user=request.user).exists():
            return fail("ALREADY_APPLIED", "You already have a rider application.", 409)
        area = Area.objects.filter(pk=to_int(d.get("area")), is_active=True).first()
        vehicle = d.get("vehicle_type", Rider.VehicleType.BODA)
        if area is None or vehicle not in Rider.VehicleType.values:
            return fail("INVALID", "Area and a valid vehicle type are required.")
        rider = Rider.objects.create(
            user=request.user, area=area, vehicle_type=vehicle,
            plate_number=str(d.get("plate_number", "")).strip().upper()[:30], status=Rider.Status.PENDING,
        )
        _grant_role(request.user, Role.RIDER)
        notify(request.user, NotificationCategory.REGISTRATION, "Application received",
               "Upload your documents so an area agent can verify you.")
        return ok({"id": rider.pk, "status": rider.status}, 201)


class RiderDocumentsView(Throttled):
    """POST multipart {doc_type, file}. Files go to PRIVATE storage."""

    permission_classes = [IsAuthenticated, IsRider]

    def post(self, request):
        rider = get_object_or_404(Rider, user=request.user)
        doc_type = request.data.get("doc_type", "")
        upload = request.FILES.get("file")
        if doc_type not in RiderDocument.DocType.values or upload is None:
            return fail("INVALID", "Choose a document type and a file.")
        if rider.documents.count() >= 10:
            return fail("LIMIT", "Document limit reached.")
        try:
            cleaned = clean_document(upload)
        except ValidationError as exc:
            return fail("INVALID_FILE", "; ".join(exc.messages))
        doc = RiderDocument(rider=rider, doc_type=doc_type, uploaded_by=request.user)
        doc.file.save(cleaned.name, cleaned, save=True)
        return ok({"id": doc.pk, "doc_type": doc.doc_type}, 201)


def rider_document_download(request, doc_id):
    """Owner, an agent covering the rider's area, or an admin — nobody else."""
    from django.contrib.auth.decorators import login_required

    @login_required
    def _inner(request):
        doc = get_object_or_404(RiderDocument.objects.select_related("rider"), pk=doc_id)
        user = request.user
        allowed = (
            user.pk == doc.rider.user_id
            or user.is_admin()
            or Agent.objects.filter(user=user, areas=doc.rider.area_id).exists()
        )
        if not allowed:
            raise Http404()
        resp = FileResponse(doc.file.open("rb"), as_attachment=True)
        resp["X-Content-Type-Options"] = "nosniff"
        resp["Cache-Control"] = "private, no-store"
        return resp

    return _inner(request)


# --------------------------------------------------------------- offers --

class OfferImageView(Throttled):
    """POST /api/v1/merchant/offers/<id>/image/ (multipart: image)"""

    permission_classes = [IsAuthenticated, IsMerchant]

    def post(self, request, offer_id):
        offer = get_object_or_404(Offer, pk=offer_id, merchant__user=request.user)
        upload = request.FILES.get("image")
        if upload is None:
            return fail("INVALID", "Choose an image.")
        if offer.images.count() >= 5:
            return fail("LIMIT", "An offer can have up to 5 photos.")
        try:
            cleaned = clean_image(upload)
        except ValidationError as exc:
            return fail("INVALID_FILE", "; ".join(exc.messages))
        img = OfferImage(offer=offer, is_primary=not offer.images.exists())
        img.image.save(cleaned.name, cleaned, save=True)
        return ok({"id": img.pk}, 201)


class OfferInteractView(Throttled):
    """POST /api/v1/member/offers/<id>/interact/ {kind} — feeds merchant stats."""

    permission_classes = [IsAuthenticated, IsMember]
    throttle_scope = "interact"
    ALLOWED = {"view", "call", "whatsapp", "delivery_request_click"}

    def post(self, request, offer_id):
        kind = request.data.get("kind")
        if kind not in self.ALLOWED:
            return fail("INVALID", "Unknown interaction.")
        offer = Offer.objects.filter(pk=offer_id, status=Offer.Status.ACTIVE).first()
        if offer is None:
            return fail("NOT_FOUND", "Offer not found.", 404)
        if kind == "view":
            # one counted view per member per offer per hour
            recent = OfferInteraction.objects.filter(
                offer=offer, user=request.user, kind="view",
                created_at__gte=timezone.now() - timedelta(hours=1),
            ).exists()
            if recent:
                return ok({"counted": False})
            Offer.objects.filter(pk=offer.pk).update(views_count=offer.views_count + 1)
        OfferInteraction.objects.create(offer=offer, user=request.user, kind=kind)
        return ok({"counted": True}, 201)


# -------------------------------------------------------- notifications --

class MarkAllReadView(Throttled):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        n = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return ok({"marked": n})


# ---------------------------------------------------------------- agent --

class AgentCompleteTaskView(Throttled):
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_scope = "agent_action"

    def post(self, request, task_id):
        task = get_object_or_404(AgentTask, pk=task_id, agent__user=request.user)
        if task.status != AgentTask.Status.OPEN:
            return fail("NOT_OPEN", "This task is not open.")
        task.status = AgentTask.Status.DONE
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "completed_at"])
        return ok({"id": task.pk, "status": task.status})


# ---------------------------------------------------------------- admin --

def cap(name):
    return HasCapability.for_capability(name)


class AdminView(Throttled):
    throttle_scope = "agent_action"
    required = None

    def get_permissions(self):
        return [IsAuthenticated(), cap(self.required)()]


class AdminOfferActionView(AdminView):
    required = "offers_moderate"
    ACTIONS = {
        "approve": ({Offer.Status.PENDING, Offer.Status.PAUSED, Offer.Status.REPORTED}, Offer.Status.ACTIVE),
        "reject": ({Offer.Status.PENDING, Offer.Status.REPORTED}, Offer.Status.REJECTED),
        "pause": ({Offer.Status.ACTIVE, Offer.Status.REPORTED}, Offer.Status.PAUSED),
    }

    @transaction.atomic
    def post(self, request, offer_id, action):
        if action not in self.ACTIONS:
            return fail("INVALID", "Unknown action.", 404)
        offer = get_object_or_404(Offer.objects.select_for_update(), pk=offer_id)
        allowed_from, new = self.ACTIONS[action]
        if offer.status not in allowed_from:
            return fail("BAD_STATE", f"Can't {action} an offer that is {offer.get_status_display().lower()}.")
        old = offer.status
        offer.status = new
        offer.save(update_fields=["status"])
        audit(request, f"offer_{action}", offer, from_status=old, reason=str(request.data.get("reason", ""))[:300])
        notify(offer.merchant.user, NotificationCategory.OFFER, f"Offer {new}",
               f"Your offer “{offer.item_name}” is now {new}.")
        return ok({"id": offer.pk, "status": offer.status})


class _AdminVerifyBase(AdminView):
    """Admin override of the agent verification flow (no agent fee is paid)."""

    model = None
    verification_model = None
    fk = None

    @transaction.atomic
    def post(self, request, pk):
        outcome = request.data.get("outcome")
        if outcome not in (self.model.Status.VERIFIED, self.model.Status.REJECTED, self.model.Status.SUSPENDED):
            return fail("INVALID", "Outcome must be verified, rejected or suspended.")
        obj = get_object_or_404(self.model.objects.select_for_update(), pk=pk)
        notes = str(request.data.get("notes", ""))[:1000]
        self.verification_model.objects.create(
            **{self.fk: obj}, performed_by=request.user, outcome=outcome,
            checklist={"admin_override": True}, notes=notes,
        )
        obj.status = outcome
        if outcome == self.model.Status.VERIFIED:
            obj.verified_by = request.user
            obj.verified_at = timezone.now()
            obj.save(update_fields=["status", "verified_by", "verified_at"])
        else:
            obj.save(update_fields=["status"])
        audit(request, f"{self.fk}_{outcome}", obj, notes=notes)
        notify(obj.user, NotificationCategory.REGISTRATION, f"Account {outcome}",
               f"Your {self.fk} account is now {outcome}." + (f" Note: {notes}" if notes else ""))
        return ok({"id": obj.pk, "status": obj.status})


class AdminVerifyMerchantView(_AdminVerifyBase):
    required = "merchant_verify"
    model, verification_model, fk = Merchant, MerchantVerification, "merchant"


class AdminVerifyRiderView(_AdminVerifyBase):
    required = "rider_verify"
    model, verification_model, fk = Rider, RiderVerification, "rider"


class AdminSettingView(AdminView):
    """PATCH /api/v1/admin/settings/<key>/ {value?, is_active?}"""

    required = "settings_manage"

    def patch(self, request, key):
        row = get_object_or_404(SystemSetting, key=key)
        old = row.value
        if "value" in request.data:
            value = str(request.data["value"]).strip()
            if not value or len(value) > 500:
                return fail("INVALID", "Value is required (max 500 chars).")
            if row.key.endswith(("percent", "_ugx", "fee", "price")) or row.key.startswith(("delivery.fare", "withdrawal", "subscription")):
                d = to_decimal(value)
                if d is None or d < 0:
                    return fail("INVALID", "This setting must be a non-negative number.")
            row.value = value
        if "is_active" in request.data:
            row.is_active = to_bool(request.data["is_active"])
        row.save()
        audit(request, "setting_changed", row, key=key, old=old, new=row.value)
        return ok({"key": row.key, "value": row.value, "is_active": row.is_active})


class AdminPlanView(AdminView):
    required = "fees_manage"

    def patch(self, request, plan_id):
        plan = get_object_or_404(SubscriptionPlan, pk=plan_id)
        old = {"price": str(plan.price), "active": plan.is_active}
        if "price" in request.data:
            price = to_decimal(request.data["price"])
            if price is None or price <= 0:
                return fail("INVALID", "Price must be a positive number.")
            plan.price = price
        if "is_active" in request.data:
            plan.is_active = to_bool(request.data["is_active"])
        plan.save()
        audit(request, "plan_changed", plan, old=old, new={"price": str(plan.price), "active": plan.is_active})
        return ok({"id": plan.pk, "price": str(plan.price), "is_active": plan.is_active})


class AdminAreasView(AdminView):
    required = "content_manage"

    def post(self, request):
        name = str(request.data.get("name", "")).strip()[:120]
        if len(name) < 2:
            return fail("INVALID", "Area name is required.")
        if Area.objects.filter(name__iexact=name).exists():
            return fail("DUPLICATE", "That area already exists.", 409)
        area = Area.objects.create(name=name, is_launch_area=to_bool(request.data.get("is_launch_area", True)))
        audit(request, "area_created", area)
        return ok({"id": area.pk}, 201)


class AdminAreaToggleView(AdminView):
    required = "content_manage"

    def post(self, request, area_id):
        area = get_object_or_404(Area, pk=area_id)
        area.is_active = not area.is_active
        area.save(update_fields=["is_active"])
        audit(request, "area_toggled", area, active=area.is_active)
        return ok({"id": area.pk, "is_active": area.is_active})


class AdminCategoriesView(AdminView):
    required = "content_manage"

    def post(self, request):
        label = str(request.data.get("label", "")).strip()[:100]
        key = str(request.data.get("key", "")).strip().lower()[:50]
        if len(label) < 2 or not key.replace("-", "").replace("_", "").isalnum():
            return fail("INVALID", "A label and a simple key (letters, numbers, - _) are required.")
        if OfferCategory.objects.filter(key=key).exists():
            return fail("DUPLICATE", "That key already exists.", 409)
        cat = OfferCategory.objects.create(key=key, label=label, emoji=str(request.data.get("emoji", ""))[:8])
        audit(request, "category_created", cat)
        return ok({"id": cat.pk}, 201)


class AdminPickupPointsView(AdminView):
    required = "content_manage"

    def post(self, request):
        area = Area.objects.filter(pk=to_int(request.data.get("area")), is_active=True).first()
        name = str(request.data.get("name", "")).strip()[:150]
        address = str(request.data.get("address", "")).strip()[:255]
        if area is None or len(name) < 2 or not address:
            return fail("INVALID", "Name, area and address are required.")
        pp = PickupPoint.objects.create(
            name=name, area=area, address=address, created_by=request.user,
            contact_phone=str(request.data.get("contact_phone", ""))[:20],
            opening_hours=str(request.data.get("opening_hours", ""))[:120],
        )
        audit(request, "pickup_point_created", pp)
        return ok({"id": pp.pk}, 201)


class AdminPickupToggleView(AdminView):
    required = "content_manage"

    def post(self, request, pp_id):
        pp = get_object_or_404(PickupPoint, pk=pp_id)
        pp.is_active = not pp.is_active
        pp.save(update_fields=["is_active"])
        audit(request, "pickup_point_toggled", pp, active=pp.is_active)
        return ok({"id": pp.pk, "is_active": pp.is_active})


class AdminAgentTasksView(AdminView):
    required = "agent_manage"

    def post(self, request):
        agent = Agent.objects.filter(pk=to_int(request.data.get("agent")), status=Agent.Status.ACTIVE).first()
        title = str(request.data.get("title", "")).strip()[:150]
        kind = request.data.get("kind", AgentTask.Kind.OTHER)
        if agent is None or len(title) < 3 or kind not in AgentTask.Kind.values:
            return fail("INVALID", "Pick an active agent, a kind and a title.")
        due = parse_datetime(request.data["due_at"]) if request.data.get("due_at") else None
        area = Area.objects.filter(pk=to_int(request.data.get("area"))).first()
        task = AgentTask.objects.create(
            agent=agent, kind=kind, title=title, description=str(request.data.get("description", ""))[:2000],
            due_at=due, area=area, created_by=request.user,
        )
        audit(request, "agent_task_created", task, agent=agent.pk)
        notify(agent.user, NotificationCategory.ANNOUNCEMENT, "New task", title)
        return ok({"id": task.pk}, 201)


class AdminAgentTaskCancelView(AdminView):
    required = "agent_manage"

    def post(self, request, task_id):
        task = get_object_or_404(AgentTask, pk=task_id, status=AgentTask.Status.OPEN)
        task.status = AgentTask.Status.CANCELLED
        task.save(update_fields=["status"])
        audit(request, "agent_task_cancelled", task)
        return ok({"id": task.pk})


class AdminBroadcastView(AdminView):
    """POST {title, message, audience: all|member|merchant|rider|agent, area?}"""

    required = "notifications_broadcast"
    throttle_scope = "write"
    MAX_RECIPIENTS = 5000

    def post(self, request):
        title = str(request.data.get("title", "")).strip()[:150]
        message = str(request.data.get("message", "")).strip()[:500]
        audience = request.data.get("audience", "all")
        if len(title) < 3 or len(message) < 3:
            return fail("INVALID", "A title and message are required.")
        users = User.objects.filter(is_active=True)
        if audience in ("member", "merchant", "rider", "agent"):
            from django.db.models import Q

            users = users.filter(Q(role=audience) | Q(assigned_roles__role=audience, assigned_roles__is_active=True))
        elif audience != "all":
            return fail("INVALID", "Unknown audience.")
        area_id = to_int(request.data.get("area"))
        if area_id:
            users = users.filter(
                models_q_area(area_id)
            )
        users = users.distinct()[: self.MAX_RECIPIENTS]
        count = 0
        for u in users:
            notify(u, NotificationCategory.ANNOUNCEMENT, title, message)
            count += 1
        AuditLog.objects.create(
            actor=request.user, action="broadcast_sent", object_type="Notification", object_id="",
            ip_address=get_client_ip(request), metadata={"audience": audience, "area": area_id, "recipients": count, "title": title},
        )
        return ok({"recipients": count})


def models_q_area(area_id):
    from django.db.models import Q

    return (
        Q(member_profile__area_id=area_id) | Q(merchant_profile__area_id=area_id)
        | Q(rider_profile__area_id=area_id) | Q(agent_profile__areas=area_id)
    )
