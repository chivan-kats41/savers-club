from django.db.models import Sum
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasCapability
from claims.models import OfferClaim
from members.models import Member
from merchants.models import Merchant
from offers.models import Offer
from payments.models import Payment, Withdrawal
from savings.models import SavingsRecord
from subscriptions.models import Subscription

CanViewReports = HasCapability.for_capability("reports_view")


class AdminReportsSummaryView(APIView):
    """GET /api/v1/admin/reports/summary/ — every figure is a live query,
    per spec section 63 ('do not use static data')."""

    permission_classes = [IsAuthenticated, CanViewReports]

    def get(self, request):
        data = {
            "members_total": Member.objects.count(),
            "subscriptions_active": Subscription.objects.filter(status=Subscription.Status.ACTIVE).count(),
            "merchants_total": Merchant.objects.count(),
            "merchants_verified": Merchant.objects.filter(status=Merchant.Status.VERIFIED).count(),
            "offers_active": Offer.objects.filter(status=Offer.Status.ACTIVE).count(),
            "claims_total": OfferClaim.objects.count(),
            "claims_redeemed": OfferClaim.objects.filter(status=OfferClaim.Status.REDEEMED).count(),
            "confirmed_savings_total": str(SavingsRecord.objects.aggregate(t=Sum("saving_amount"))["t"] or 0),
            "payments_success": Payment.objects.filter(status=Payment.Status.SUCCESS).count(),
            "payments_failed": Payment.objects.filter(status=Payment.Status.FAILED).count(),
            "payments_pending": Payment.objects.filter(status=Payment.Status.PENDING).count(),
            "payment_volume_success": str(
                Payment.objects.filter(status=Payment.Status.SUCCESS).aggregate(t=Sum("amount"))["t"] or 0
            ),
            "withdrawals_completed": Withdrawal.objects.filter(status=Withdrawal.Status.COMPLETED).count(),
            "withdrawal_volume_completed": str(
                Withdrawal.objects.filter(status=Withdrawal.Status.COMPLETED).aggregate(t=Sum("net_amount"))["t"] or 0
            ),
        }
        return Response({"success": True, "data": data})
