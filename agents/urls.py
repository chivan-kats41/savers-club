from django.urls import path

from . import views

app_name = "agents"

urlpatterns = [
    path("agent/dashboard/", views.AgentDashboardView.as_view(), name="dashboard"),
    path("agent/merchants-to-verify/", views.MerchantsToVerifyView.as_view(), name="merchants_to_verify"),
    path("agent/merchants/<int:merchant_id>/verify/", views.VerifyMerchantView.as_view(), name="verify_merchant"),
    path("agent/riders-to-verify/", views.RidersToVerifyView.as_view(), name="riders_to_verify"),
    path("agent/riders/<int:rider_id>/verify/", views.VerifyRiderView.as_view(), name="verify_rider"),
    path("agent/prices/", views.PricesView.as_view(), name="prices"),
    path("agent/earnings/", views.AgentEarningsView.as_view(), name="earnings"),
    path("admin/agents/", views.AdminAgentsView.as_view(), name="admin_agents"),
    path("agent/offers-to-approve/", views.OffersToApproveView.as_view(), name="offers_to_approve"),
    path("agent/offers/<int:offer_id>/approve/", views.ApproveOfferView.as_view(), name="approve_offer"),
    path("agent/offers/<int:offer_id>/reject/", views.RejectOfferView.as_view(), name="reject_offer"),
]
