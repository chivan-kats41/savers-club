from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.permissions import IsRole
from members.models import Member

from .models import Subscription
from .serializers import SubscriptionSerializer
from .services import SubscriptionError, initiate_renewal, pause_subscription

IsMember = IsRole.for_roles("member")


class MySubscriptionView(APIView):
    """GET /api/v1/member/subscription/ — the requesting member's most
    recent subscription. Deliberately takes no id from the URL: there is
    no path for a member to ever reference another member's subscription,
    which is the strongest IDOR defense available (see spec section 54).
    """
    serializer_class = SubscriptionSerializer

    permission_classes = [IsAuthenticated, IsMember]

    def get(self, request):
        member = get_object_or_404(Member, user=request.user)
        subscription = Subscription.objects.filter(member=member).order_by("-created_at").first()
        if subscription is None:
            return Response({"success": True, "data": None})
        return Response({"success": True, "data": SubscriptionSerializer(subscription).data})


class RenewSubscriptionView(APIView):
    """POST /api/v1/member/subscription/renew/ — opens a pending payment.
    Never activates anything itself; see subscriptions.services.confirm_payment.
    """

    permission_classes = [IsAuthenticated, IsMember]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "payment_initiate"

    def post(self, request):
        member = get_object_or_404(Member, user=request.user)
        try:
            payment = initiate_renewal(member)
        except SubscriptionError as exc:
            return Response(
                {"success": False, "error": {"code": "RENEWAL_FAILED", "message": '; '.join(exc.messages), "details": {}}},
                status=400,
            )
        return Response(
            {
                "success": True,
                "data": {
                    "payment_id": str(payment.pk),
                    "external_reference": str(payment.external_reference),
                    "amount": str(payment.amount),
                    "status": payment.status,
                    "next_action": "WAIT_FOR_PROVIDER",
                },
            },
            status=201,
        )


class PauseSubscriptionView(APIView):
    """POST /api/v1/member/subscription/pause/"""
    serializer_class = SubscriptionSerializer

    permission_classes = [IsAuthenticated, IsMember]

    def post(self, request):
        member = get_object_or_404(Member, user=request.user)
        try:
            subscription = pause_subscription(member)
        except SubscriptionError as exc:
            return Response(
                {"success": False, "error": {"code": "PAUSE_FAILED", "message": '; '.join(exc.messages), "details": {}}},
                status=400,
            )
        return Response({"success": True, "data": SubscriptionSerializer(subscription).data})
