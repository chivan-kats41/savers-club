from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsRole

from .models import Member, ReferralReward
from .serializers import ReferralRewardSerializer

IsMember = IsRole.for_roles("member")


class MyReferralsView(APIView):
    """GET /api/v1/member/referrals/ — my referral code, who I've
    referred, and rewards earned (pending + credited)."""

    permission_classes = [IsAuthenticated, IsMember]
    serializer_class = ReferralRewardSerializer

    def get(self, request):
        member = get_object_or_404(Member, user=request.user)
        rewards = ReferralReward.objects.filter(referrer=member)
        referred_count = member.referrals.count()
        totals = rewards.aggregate(
            pending=Sum("amount", filter=Q(status=ReferralReward.Status.PENDING)),
            credited=Sum("amount", filter=Q(status=ReferralReward.Status.CREDITED)),
        )
        return Response(
            {
                "success": True,
                "data": {
                    "referral_code": member.referral_code,
                    "referred_count": referred_count,
                    "pending_reward_total": str(totals["pending"] or 0),
                    "credited_reward_total": str(totals["credited"] or 0),
                    "rewards": ReferralRewardSerializer(rewards, many=True).data,
                },
            }
        )
