from decimal import Decimal, InvalidOperation

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.permissions import IsRole
from members.models import Member
from merchants.models import Merchant

from .models import MemberRequest
from .serializers import MemberRequestSerializer, MerchantVisibleRequestSerializer
from .services import ItemRequestError, cancel_request, file_request, fulfill_request, respond_to_request

IsMember = IsRole.for_roles("member")
IsMerchant = IsRole.for_roles("merchant")


def _error(code, exc, status=400):
    message = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
    return Response({"success": False, "error": {"code": code, "message": message, "details": {}}}, status=status)


def _parse_decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


class MemberRequestsView(APIView):
    """GET/POST /api/v1/member/requests/"""

    permission_classes = [IsAuthenticated, IsMember]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"
    serializer_class = MemberRequestSerializer

    def get(self, request):
        member = get_object_or_404(Member, user=request.user)
        requests_qs = MemberRequest.objects.filter(member=member)
        return Response({"success": True, "data": MemberRequestSerializer(requests_qs, many=True).data})

    def post(self, request):
        member = get_object_or_404(Member, user=request.user)
        try:
            req = file_request(
                member, request.data.get("item_name", ""), request.data.get("description", ""),
                _parse_decimal(request.data.get("max_budget")),
            )
        except ItemRequestError as exc:
            return _error("REQUEST_FAILED", exc)
        return Response({"success": True, "data": MemberRequestSerializer(req).data}, status=201)


class FulfillRequestView(APIView):
    permission_classes = [IsAuthenticated, IsMember]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"
    serializer_class = MemberRequestSerializer

    def post(self, request, request_id):
        member = get_object_or_404(Member, user=request.user)
        try:
            req = fulfill_request(member, request_id, request.data.get("response_id"))
        except ItemRequestError as exc:
            return _error("FULFILL_FAILED", exc)
        return Response({"success": True, "data": MemberRequestSerializer(req).data})


class CancelRequestView(APIView):
    permission_classes = [IsAuthenticated, IsMember]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"
    serializer_class = MemberRequestSerializer

    def post(self, request, request_id):
        member = get_object_or_404(Member, user=request.user)
        try:
            req = cancel_request(member, request_id)
        except ItemRequestError as exc:
            return _error("CANCEL_FAILED", exc)
        return Response({"success": True, "data": MemberRequestSerializer(req).data})


class MerchantOpenRequestsView(APIView):
    """GET /api/v1/merchant/requests/ — open requests in the merchant's area."""

    permission_classes = [IsAuthenticated, IsMerchant]
    serializer_class = MerchantVisibleRequestSerializer

    def get(self, request):
        merchant = get_object_or_404(Merchant, user=request.user)
        requests_qs = MemberRequest.objects.filter(
            area=merchant.area, status__in=[MemberRequest.Status.OPEN, MemberRequest.Status.RESPONDED]
        )
        return Response({"success": True, "data": MerchantVisibleRequestSerializer(requests_qs, many=True).data})


class RespondToRequestView(APIView):
    permission_classes = [IsAuthenticated, IsMerchant]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"
    serializer_class = MerchantVisibleRequestSerializer

    def post(self, request, request_id):
        merchant = get_object_or_404(Merchant, user=request.user)
        try:
            response = respond_to_request(
                merchant, request_id, request.data.get("message", ""), _parse_decimal(request.data.get("price"))
            )
        except ItemRequestError as exc:
            return _error("RESPOND_FAILED", exc)
        from .serializers import RequestResponseSerializer

        return Response({"success": True, "data": RequestResponseSerializer(response).data}, status=201)
