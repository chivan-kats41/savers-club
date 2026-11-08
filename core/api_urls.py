from django.urls import path

from .admin_reports import AdminReportsSummaryView

app_name = "core_api"

urlpatterns = [
    path("admin/reports/summary/", AdminReportsSummaryView.as_view(), name="admin_reports_summary"),
]
