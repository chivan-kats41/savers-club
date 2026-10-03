from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.permissions import IsRole
from agents.models import Agent
from members.models import Member

from .models import Complaint
from .serializers import ComplaintSerializer
from .services import ComplaintError, escalate_complaint, file_complaint, resolve_complaint, start_investigating

IsMember = IsRole.for_roles("member")
IsAgent = IsRole.for_roles("agent")


def _error(code, exc, status=400):
    message = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
    return Response({"success": False, "error": {"code": code, "message": message, "details": {}}}, status=status)


class MemberComplaintsView(APIView):
    """GET/POST /api/v1/member/complaints/"""
    serializer_class = ComplaintSerializer

    permission_classes = [IsAuthenticated, IsMember]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"

    def get(self, request):
        member = get_object_or_404(Member, user=request.user)
        complaints = Complaint.objects.filter(member=member)
        return Response({"success": True, "data": ComplaintSerializer(complaints, many=True).data})

    def post(self, request):
        member = get_object_or_404(Member, user=request.user)
        try:
            complaint = file_complaint(
                member, request.data.get("subject", ""), request.data.get("description", "")
            )
        except ComplaintError as exc:
            return _error("COMPLAINT_FAILED", exc)
        return Response({"success": True, "data": ComplaintSerializer(complaint).data}, status=201)


class AgentComplaintsView(APIView):
    """GET /api/v1/agent/complaints/ — open/investigating complaints in this agent's areas."""
    serializer_class = ComplaintSerializer

    permission_classes = [IsAuthenticated, IsAgent]

    def get(self, request):
        agent = get_object_or_404(Agent, user=request.user)
        area_ids = agent.areas.values_list("id", flat=True)
        complaints = Complaint.objects.filter(
            area_id__in=area_ids, status__in=[Complaint.Status.OPEN, Complaint.Status.INVESTIGATING]
        )
        return Response({"success": True, "data": ComplaintSerializer(complaints, many=True).data})


class StartInvestigatingView(APIView):
    serializer_class = ComplaintSerializer
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"

    def post(self, request, complaint_id):
        agent = get_object_or_404(Agent, user=request.user)
        try:
            complaint = start_investigating(agent, complaint_id)
        except ComplaintError as exc:
            return _error("START_FAILED", exc)
        return Response({"success": True, "data": ComplaintSerializer(complaint).data})


class ResolveComplaintView(APIView):
    serializer_class = ComplaintSerializer
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"

    def post(self, request, complaint_id):
        agent = get_object_or_404(Agent, user=request.user)
        try:
            complaint = resolve_complaint(request.user, agent, complaint_id, request.data.get("resolution_note", ""))
        except ComplaintError as exc:
            return _error("RESOLVE_FAILED", exc)
        return Response({"success": True, "data": ComplaintSerializer(complaint).data})


class EscalateComplaintView(APIView):
    serializer_class = ComplaintSerializer
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"

    def post(self, request, complaint_id):
        agent = get_object_or_404(Agent, user=request.user)
        try:
            complaint = escalate_complaint(agent, complaint_id, request.data.get("note", ""))
        except ComplaintError as exc:
            return _error("ESCALATE_FAILED", exc)
        return Response({"success": True, "data": ComplaintSerializer(complaint).data})
