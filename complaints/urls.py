from django.urls import path

from . import views

app_name = "complaints"

urlpatterns = [
    path("member/complaints/", views.MemberComplaintsView.as_view(), name="member_complaints"),
    path("agent/complaints/", views.AgentComplaintsView.as_view(), name="agent_complaints"),
    path("agent/complaints/<int:complaint_id>/start/", views.StartInvestigatingView.as_view(), name="start_investigating"),
    path("agent/complaints/<int:complaint_id>/resolve/", views.ResolveComplaintView.as_view(), name="resolve_complaint"),
    path("agent/complaints/<int:complaint_id>/escalate/", views.EscalateComplaintView.as_view(), name="escalate_complaint"),
]
