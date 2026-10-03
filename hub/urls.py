from django.urls import path

from . import views
from .api import rider_document_download as api_download

urlpatterns = [
    path("", views.landing, name="landing"),
    path("member/", views.member, name="member"),
    path("merchant/", views.merchant, name="merchant"),
    path("rider/", views.rider, name="rider"),
    path("agent/", views.agent, name="agent"),

    path("admin-console/", views.admin_index, name="admin_index"),
    path("admin-console/members/", views.admin_members, name="admin_members"),
    path("admin-console/subscriptions/", views.admin_subscriptions, name="admin_subscriptions"),
    path("admin-console/merchants/", views.admin_merchants, name="admin_merchants"),
    path("admin-console/offers/", views.admin_offers, name="admin_offers"),
    path("admin-console/claims/", views.admin_claims, name="admin_claims"),
    path("admin-console/redemptions/", views.admin_redemptions, name="admin_redemptions"),
    path("admin-console/riders/", views.admin_riders, name="admin_riders"),
    path("admin-console/routes/", views.admin_routes, name="admin_routes"),
    path("admin-console/pickup/", views.admin_pickup, name="admin_pickup"),
    path("admin-console/agents/", views.admin_agents, name="admin_agents"),
    path("admin-console/tasks/", views.admin_tasks, name="admin_tasks"),
    path("admin-console/prices/", views.admin_prices, name="admin_prices"),
    path("admin-console/payments/", views.admin_payments, name="admin_payments"),
    path("admin-console/settlements/", views.admin_settlements, name="admin_settlements"),
    path("admin-console/complaints/", views.admin_complaints, name="admin_complaints"),
    path("admin-console/notifications/", views.admin_notifications, name="admin_notifications"),
    path("admin-console/reports/", views.admin_reports, name="admin_reports"),
    path("admin-console/settings/", views.admin_settings, name="admin_settings"),
    path("notifications/", views.notifications_page, name="notifications"),
    path("payments/return/", views.payment_return, name="payment_return"),
    path("become-a-merchant/", views.apply_merchant, name="apply_merchant"),
    path("become-a-rider/", views.apply_rider, name="apply_rider"),
    path("files/rider-documents/<int:doc_id>/", api_download, name="rider_document"),
]
