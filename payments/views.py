from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.permissions import IsRole
from members.models import Member
from riders.models import Rider

from .models import Payment, Withdrawal
from .serializers import PaymentSerializer, WithdrawalSerializer
from .services.payment_flow import PaymentError, initiate_subscription_payment, process_collection_callback
from .services.reconciliation import OPEN_PAYMENT_STATUSES, reconcile_payment
from .services.withdrawal_flow import WithdrawalError, available_rider_balance, process_disbursement_callback, request_rider_withdrawal

IsMember = IsRole.for_roles("member")
IsRider = IsRole.for_roles("rider")


class InitiatePaymentView(APIView):
    """POST /api/v1/payments/initiate/
    body: {"purpose": "subscription", "method": "mobile_money"|"card", "phone": "...", "email": "..."}
    Unified entry point per spec section 10 — dispatches by `purpose`.
    Only "subscription" is wired up so far.
    """
    serializer_class = PaymentSerializer

    permission_classes = [IsAuthenticated, IsMember]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "payment_initiate"

    def post(self, request):
        purpose = request.data.get("purpose")
        method = request.data.get("method")

        if purpose != Payment.Purpose.SUBSCRIPTION:
            return Response(
                {"success": False, "error": {"code": "UNSUPPORTED_PURPOSE", "message": f"'{purpose}' is not supported yet.", "details": {}}},
                status=400,
            )
        if method not in Payment.Method.values:
            return Response(
                {"success": False, "error": {"code": "INVALID_METHOD", "message": "method must be mobile_money or card.", "details": {}}},
                status=400,
            )

        member = get_object_or_404(Member, user=request.user)
        try:
            payment = initiate_subscription_payment(
                member, method, payer_phone=request.data.get("phone", ""),
                payer_email=request.data.get("email") or request.user.email or ""
            )
        except PaymentError as exc:
            message = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            return Response(
                {"success": False, "error": {"code": "PAYMENT_FAILED", "message": message, "details": {}}}, status=400
            )

        data = PaymentSerializer(payment).data
        data["next_action"] = "REDIRECT" if payment.redirect_url else "WAIT_FOR_PROVIDER"
        return Response({"success": True, "data": data}, status=201)


class PaymentStatusView(APIView):
    """GET /api/v1/payments/<id>/ — owner-scoped."""
    serializer_class = PaymentSerializer

    permission_classes = [IsAuthenticated]

    def get(self, request, payment_id):
        payment = get_object_or_404(Payment, pk=payment_id, user=request.user)
        # Don't wait for a callback: while the payment is open, ask ioTec directly (at most once every
        # few seconds per payment). This also makes card returns and local development (no public
        # callback URL) work. ioTec's answer, never the browser's, decides the outcome.
        if payment.status in OPEN_PAYMENT_STATUSES:
            from django.core.cache import cache

            if cache.add(f"pay-refresh:{payment.pk}", 1, timeout=4):
                payment = reconcile_payment(payment)
        return Response({"success": True, "data": PaymentSerializer(payment).data})


def _callback_secret_ok(request) -> bool:
    """Shared secret ioTec sends as its "Security Header". Accepts `X-Callback-Secret: <v>` or
    `Authorization: Bearer <v>`. Fails CLOSED outside DEBUG: an open callback URL would let anyone
    make us call ioTec's API on demand."""
    import hmac

    secret = settings.IOTEC_CALLBACK_SECRET
    if not secret:
        return bool(settings.DEBUG)
    candidates = [request.headers.get("X-Callback-Secret", "")]
    auth = request.headers.get("Authorization", "")
    candidates.append(auth[7:] if auth.lower().startswith("bearer ") else auth)
    return any(c and hmac.compare_digest(c.encode(), secret.encode()) for c in candidates)


def _unauthorized():
    return Response(
        {"success": False, "error": {"code": "UNAUTHORIZED", "message": "Invalid callback credentials.", "details": {}}},
        status=401,
    )


class CollectionCallbackView(APIView):
    """POST /api/v1/payments/callback/iotec/collection/ — called by ioTec, not the browser, so no
    session/CSRF. The body is only used to LOCATE the payment; the status applied always comes from
    ioTec's status API."""
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "payment_callback"

    def post(self, request):
        if not _callback_secret_ok(request):
            return _unauthorized()
        from .services.reconciliation import verified_collection_callback

        verified_collection_callback(request.data)
        return Response({"success": True})


class DisbursementCallbackView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "payment_callback"

    def post(self, request):
        if not _callback_secret_ok(request):
            return _unauthorized()
        from .services.reconciliation import verified_disbursement_callback

        verified_disbursement_callback(request.data)
        return Response({"success": True})


class IotecCallbackView(APIView):
    """POST /api/iotec/callback — ONE URL for everything. Register this single URL in the ioTec Pay portal
    and it handles both collection (money in) and disbursement (money out) events: we look the externalId
    up in both tables."""
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "payment_callback"

    def post(self, request):
        if not _callback_secret_ok(request):
            return _unauthorized()
        from .services.reconciliation import verified_collection_callback, verified_disbursement_callback

        payload = request.data if isinstance(request.data, dict) else {}
        ext = payload.get("externalId") or payload.get("external_id")
        try:
            if ext and Withdrawal.objects.filter(internal_reference=ext).exists():
                verified_disbursement_callback(payload)
            else:
                verified_collection_callback(payload)
        except Exception:  # never make ioTec retry-storm us over our own bug; reconciliation will catch up
            import logging

            logging.getLogger("payments").exception("Unhandled error processing ioTec callback")
        return Response({"success": True})


class RiderBalanceView(APIView):
    """GET /api/v1/rider/balance/ — funds available to withdraw right now."""

    permission_classes = [IsAuthenticated, IsRider]

    def get(self, request):
        rider = get_object_or_404(Rider, user=request.user)
        return Response({"success": True, "data": {"available_balance": str(available_rider_balance(rider))}})


class RequestWithdrawalView(APIView):
    """POST /api/v1/rider/withdraw/  body: {"amount": "5000", "phone": "+2567..."}"""
    serializer_class = WithdrawalSerializer

    permission_classes = [IsAuthenticated, IsRider]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "withdrawal"

    def post(self, request):
        from decimal import Decimal, InvalidOperation

        rider = get_object_or_404(Rider, user=request.user)
        phone = request.data.get("phone", "")
        try:
            amount = Decimal(str(request.data.get("amount", "0")))
        except InvalidOperation:
            return Response(
                {"success": False, "error": {"code": "INVALID_AMOUNT", "message": "Invalid amount.", "details": {}}},
                status=400,
            )

        try:
            withdrawal = request_rider_withdrawal(rider, amount, phone)
        except WithdrawalError as exc:
            message = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            return Response(
                {"success": False, "error": {"code": "WITHDRAWAL_FAILED", "message": message, "details": {}}},
                status=400,
            )
        return Response({"success": True, "data": WithdrawalSerializer(withdrawal).data}, status=201)


class MyWithdrawalsView(APIView):
    """GET /api/v1/rider/withdrawals/"""
    serializer_class = WithdrawalSerializer

    permission_classes = [IsAuthenticated, IsRider]

    def get(self, request):
        withdrawals = Withdrawal.objects.filter(user=request.user)
        return Response({"success": True, "data": WithdrawalSerializer(withdrawals, many=True).data})
