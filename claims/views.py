from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.permissions import IsRole
from members.models import Member
from merchants.models import Merchant

from .models import OfferClaim
from .serializers import ClaimSerializer, MerchantClaimSerializer
from .services import ClaimError, cancel_claim, claim_offer, redeem_claim

IsMember = IsRole.for_roles("member")
IsMerchant = IsRole.for_roles("merchant")


def _error(code, exc, status=400):
    message = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
    return Response({"success": False, "error": {"code": code, "message": message, "details": {}}}, status=status)


class ClaimOfferView(APIView):
    """POST /api/v1/member/offers/<offer_id>/claim/"""
    serializer_class = ClaimSerializer

    permission_classes = [IsAuthenticated, IsMember]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "claim"

    def post(self, request, offer_id):
        member = get_object_or_404(Member, user=request.user)
        try:
            claim = claim_offer(member, offer_id)
        except ClaimError as exc:
            return _error("CLAIM_FAILED", exc)
        return Response({"success": True, "data": ClaimSerializer(claim).data}, status=201)


class MyClaimsView(APIView):
    """GET /api/v1/member/claims/"""
    serializer_class = ClaimSerializer

    permission_classes = [IsAuthenticated, IsMember]

    def get(self, request):
        member = get_object_or_404(Member, user=request.user)
        claims = OfferClaim.objects.filter(member=member).select_related("offer", "offer__merchant")
        return Response({"success": True, "data": ClaimSerializer(claims, many=True).data})


class CancelClaimView(APIView):
    """POST /api/v1/member/claims/cancel/  body: {"code": "1K-XXXX"}"""
    serializer_class = ClaimSerializer

    permission_classes = [IsAuthenticated, IsMember]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"

    def post(self, request):
        member = get_object_or_404(Member, user=request.user)
        code = request.data.get("code", "")
        try:
            claim = cancel_claim(member, code)
        except ClaimError as exc:
            return _error("CANCEL_FAILED", exc)
        return Response({"success": True, "data": ClaimSerializer(claim).data})


class RedeemClaimView(APIView):
    """POST /api/v1/merchant/claims/redeem/  body: {"code": "1K-XXXX"}
    Deliberately takes the code in the body, not a claim id in the URL —
    a merchant should never be able to enumerate claim ids belonging to
    other merchants (see spec section 54, IDOR protection)."""
    serializer_class = ClaimSerializer

    permission_classes = [IsAuthenticated, IsMerchant]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "redeem"

    def post(self, request):
        merchant = get_object_or_404(Merchant, user=request.user)
        code = request.data.get("code", "")
        try:
            claim = redeem_claim(merchant, code)
        except ClaimError as exc:
            return _error("REDEEM_FAILED", exc)
        return Response({"success": True, "data": ClaimSerializer(claim).data})


class MerchantClaimsView(APIView):
    """GET /api/v1/merchant/claims/ — only this merchant's own claims."""
    serializer_class = MerchantClaimSerializer

    permission_classes = [IsAuthenticated, IsMerchant]

    def get(self, request):
        merchant = get_object_or_404(Merchant, user=request.user)
        claims = OfferClaim.objects.filter(offer__merchant=merchant).select_related("offer", "member__user")
        return Response({"success": True, "data": MerchantClaimSerializer(claims, many=True).data})
