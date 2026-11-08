from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsRole
from members.models import Member

from .models import SavingsRecord
from .selectors import monthly_savings_history, savings_summary

IsMember = IsRole.for_roles("member")


class MySavingsView(APIView):
    """GET /api/v1/member/savings/ — confirmed/possible/monthly totals,
    all computed live from SavingsRecord + Offer (see selectors.py)."""

    permission_classes = [IsAuthenticated, IsMember]

    def get(self, request):
        member = get_object_or_404(Member, user=request.user)
        summary = savings_summary(member)
        return Response({"success": True, "data": summary})


class MySavingsHistoryView(APIView):
    """GET /api/v1/member/savings/history/ — last 6 months, oldest first."""

    permission_classes = [IsAuthenticated, IsMember]

    def get(self, request):
        member = get_object_or_404(Member, user=request.user)
        history = monthly_savings_history(member)
        return Response({"success": True, "data": history})
