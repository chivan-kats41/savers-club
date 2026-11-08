from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.models import Role, User
from accounts.permissions import HasCapability, IsRole
from core.models import Area
from merchants.models import Merchant
from offers.models import OfferCategory
from riders.models import Rider

from .models import Agent, AgentEarning, PriceRecord
from .serializers import (
    AgentEarningSerializer,
    AgentSerializer,
    MerchantToVerifySerializer,
    PriceRecordSerializer,
    RiderToVerifySerializer,
)
from .services import AgentError, submit_price, verify_merchant, verify_rider

IsAgent = IsRole.for_roles("agent")
CanManageAgents = HasCapability.for_capability("agent_manage")


def _error(code, exc, status=400):
    message = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
    return Response({"success": False, "error": {"code": code, "message": message, "details": {}}}, status=status)


class AgentDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsAgent]

    def get(self, request):
        agent = get_object_or_404(Agent, user=request.user)
        area_ids = list(agent.areas.values_list("id", flat=True))
        data = {
            "areas": list(agent.areas.values_list("name", flat=True)),
            "merchants_pending": Merchant.objects.filter(area_id__in=area_ids, status=Merchant.Status.PENDING).count(),
            "riders_pending": Rider.objects.filter(area_id__in=area_ids, status=Rider.Status.PENDING).count(),
            "earnings_total": AgentEarning.objects.filter(agent=agent).aggregate(t=Sum("amount"))["t"] or 0,
        }
        return Response({"success": True, "data": data})


class MerchantsToVerifyView(APIView):
    serializer_class = MerchantToVerifySerializer
    permission_classes = [IsAuthenticated, IsAgent]

    def get(self, request):
        agent = get_object_or_404(Agent, user=request.user)
        area_ids = agent.areas.values_list("id", flat=True)
        merchants = Merchant.objects.filter(area_id__in=area_ids, status=Merchant.Status.PENDING)
        return Response({"success": True, "data": MerchantToVerifySerializer(merchants, many=True).data})


class VerifyMerchantView(APIView):
    serializer_class = MerchantToVerifySerializer
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent_action"

    def post(self, request, merchant_id):
        agent = get_object_or_404(Agent, user=request.user)
        try:
            merchant = verify_merchant(
                agent, merchant_id,
                outcome=request.data.get("outcome", ""),
                checklist=request.data.get("checklist", {}),
                notes=request.data.get("notes", ""),
            )
        except AgentError as exc:
            return _error("VERIFY_FAILED", exc)
        return Response({"success": True, "data": MerchantToVerifySerializer(merchant).data})


class RidersToVerifyView(APIView):
    serializer_class = RiderToVerifySerializer
    permission_classes = [IsAuthenticated, IsAgent]

    def get(self, request):
        agent = get_object_or_404(Agent, user=request.user)
        area_ids = agent.areas.values_list("id", flat=True)
        riders = Rider.objects.filter(area_id__in=area_ids, status=Rider.Status.PENDING)
        return Response({"success": True, "data": RiderToVerifySerializer(riders, many=True).data})


class VerifyRiderView(APIView):
    serializer_class = RiderToVerifySerializer
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent_action"

    def post(self, request, rider_id):
        agent = get_object_or_404(Agent, user=request.user)
        try:
            rider = verify_rider(
                agent, rider_id,
                outcome=request.data.get("outcome", ""),
                checklist=request.data.get("checklist", {}),
                notes=request.data.get("notes", ""),
            )
        except AgentError as exc:
            return _error("VERIFY_FAILED", exc)
        return Response({"success": True, "data": RiderToVerifySerializer(rider).data})


class PricesView(APIView):
    serializer_class = PriceRecordSerializer
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent_action"

    def get(self, request):
        agent = get_object_or_404(Agent, user=request.user)
        records = PriceRecord.objects.filter(agent=agent)
        return Response({"success": True, "data": PriceRecordSerializer(records, many=True).data})

    def post(self, request):
        from decimal import Decimal, InvalidOperation

        agent = get_object_or_404(Agent, user=request.user)
        area = Area.objects.filter(pk=request.data.get("area_id")).first()
        category = OfferCategory.objects.filter(pk=request.data.get("category_id")).first()
        if not area or not category:
            return Response(
                {"success": False, "error": {"code": "INVALID_INPUT", "message": "Valid area_id and category_id required.", "details": {}}},
                status=400,
            )
        try:
            price = Decimal(str(request.data.get("price", "0")))
        except InvalidOperation:
            return Response(
                {"success": False, "error": {"code": "INVALID_PRICE", "message": "Invalid price.", "details": {}}},
                status=400,
            )
        try:
            record = submit_price(agent, area, category, request.data.get("item_name", ""), price)
        except AgentError as exc:
            return _error("PRICE_SUBMIT_FAILED", exc)
        return Response({"success": True, "data": PriceRecordSerializer(record).data}, status=201)


class AgentEarningsView(APIView):
    permission_classes = [IsAuthenticated, IsAgent]

    def get(self, request):
        agent = get_object_or_404(Agent, user=request.user)
        earnings = AgentEarning.objects.filter(agent=agent)
        total = earnings.aggregate(t=Sum("amount"))["t"] or 0
        return Response(
            {"success": True, "data": {"total": str(total), "records": AgentEarningSerializer(earnings, many=True).data}}
        )


class AdminAgentsView(APIView):
    """GET/POST /api/v1/admin/agents/ — onboard and list agents. Never
    is_staff-gated: requires the agent_manage capability (or SUPER_ADMIN)."""
    serializer_class = AgentSerializer

    permission_classes = [IsAuthenticated, CanManageAgents]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent_action"

    def get(self, request):
        agents = Agent.objects.all()
        return Response({"success": True, "data": AgentSerializer(agents, many=True).data})

    def post(self, request):
        user_id = request.data.get("user_id")
        phone = str(request.data.get("phone", "")).strip()
        area_ids = request.data.get("area_ids", [])
        user = get_object_or_404(User, phone=phone) if phone and not user_id else get_object_or_404(User, pk=user_id)

        if user.role != Role.AGENT:
            user.role = Role.AGENT
            user.save(update_fields=["role"])

        agent, _ = Agent.objects.get_or_create(user=user)
        if area_ids:
            agent.areas.set(Area.objects.filter(pk__in=area_ids))

        return Response({"success": True, "data": AgentSerializer(agent).data}, status=201)


class OffersToApproveView(APIView):
    """GET /api/v1/agent/offers-to-approve/"""

    permission_classes = [IsAuthenticated, IsAgent]

    def get(self, request):
        from offers.models import Offer
        from offers.serializers import MerchantOfferSerializer

        agent = get_object_or_404(Agent, user=request.user)
        area_ids = agent.areas.values_list("id", flat=True)
        offers = Offer.objects.filter(area_id__in=area_ids, status=Offer.Status.PENDING)
        return Response({"success": True, "data": MerchantOfferSerializer(offers, many=True).data})


class ApproveOfferView(APIView):
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent_action"

    def post(self, request, offer_id):
        from offers.serializers import MerchantOfferSerializer
        from .services import approve_offer

        agent = get_object_or_404(Agent, user=request.user)
        try:
            offer = approve_offer(agent, offer_id)
        except AgentError as exc:
            return _error("APPROVE_FAILED", exc)
        return Response({"success": True, "data": MerchantOfferSerializer(offer).data})


class RejectOfferView(APIView):
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent_action"

    def post(self, request, offer_id):
        from offers.serializers import MerchantOfferSerializer
        from .services import reject_offer

        agent = get_object_or_404(Agent, user=request.user)
        try:
            offer = reject_offer(agent, offer_id, request.data.get("reason", ""))
        except AgentError as exc:
            return _error("REJECT_FAILED", exc)
        return Response({"success": True, "data": MerchantOfferSerializer(offer).data})
