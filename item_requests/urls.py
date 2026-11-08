from django.urls import path

from . import views

app_name = "item_requests"

urlpatterns = [
    path("member/requests/", views.MemberRequestsView.as_view(), name="member_requests"),
    path("member/requests/<int:request_id>/fulfill/", views.FulfillRequestView.as_view(), name="fulfill_request"),
    path("member/requests/<int:request_id>/cancel/", views.CancelRequestView.as_view(), name="cancel_request"),
    path("merchant/requests/", views.MerchantOpenRequestsView.as_view(), name="merchant_open_requests"),
    path("merchant/requests/<int:request_id>/respond/", views.RespondToRequestView.as_view(), name="respond_to_request"),
]
