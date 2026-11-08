from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.permissions import IsRole
from merchants.models import Merchant
from payments.models import Payment
from payments.serializers import PaymentSerializer
from payments.services.payment_flow import PaymentError, initiate_promotion_payment

from .models import PromotionPackage, PromotionPurchase
from .serializers import PromotionPackageSerializer, PromotionPurchaseSerializer

IsMerchant = IsRole.for_roles("merchant")


class PromotionPackagesView(APIView):
    """GET /api/v1/promotions/packages/ — any merchant."""

    permission_classes = [IsAuthenticated, IsMerchant]
    serializer_class = PromotionPackageSerializer

    def get(self, request):
        packages = PromotionPackage.objects.filter(is_active=True)
        return Response({"success": True, "data": PromotionPackageSerializer(packages, many=True).data})


class PurchasePromotionView(APIView):
    """POST /api/v1/merchant/promotions/
    body: {offer_id, package_id, method, phone|email}"""

    permission_classes = [IsAuthenticated, IsMerchant]
    serializer_class = PaymentSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "payment_initiate"

    def post(self, request):
        merchant = get_object_or_404(Merchant, user=request.user)
        package = PromotionPackage.objects.filter(pk=request.data.get("package_id"), is_active=True).first()
        if package is None:
            return Response(
                {"success": False, "error": {"code": "INVALID_PACKAGE", "message": "Unknown or inactive package.", "details": {}}},
                status=400,
            )
        method = request.data.get("method")
        if method not in Payment.Method.values:
            return Response(
                {"success": False, "error": {"code": "INVALID_METHOD", "message": "method must be mobile_money or card.", "details": {}}},
                status=400,
            )

        try:
            payment = initiate_promotion_payment(
                merchant, request.data.get("offer_id"), package, method,
                payer_phone=request.data.get("phone", ""),
                payer_email=request.data.get("email") or request.user.email or "",
            )
        except PaymentError as exc:
            message = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            return Response(
                {"success": False, "error": {"code": "PROMOTION_PAYMENT_FAILED", "message": message, "details": {}}},
                status=400,
            )
        data = PaymentSerializer(payment).data
        data["next_action"] = "REDIRECT" if payment.redirect_url else "WAIT_FOR_PROVIDER"
        return Response({"success": True, "data": data}, status=201)


class MyPromotionsView(APIView):
    """GET /api/v1/merchant/promotions/ — this merchant's promotion history."""

    permission_classes = [IsAuthenticated, IsMerchant]
    serializer_class = PromotionPurchaseSerializer

    def get(self, request):
        merchant = get_object_or_404(Merchant, user=request.user)
        purchases = PromotionPurchase.objects.filter(merchant=merchant)
        return Response({"success": True, "data": PromotionPurchaseSerializer(purchases, many=True).data})
