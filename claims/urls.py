from django.urls import path

from . import views

app_name = "claims"

urlpatterns = [
    path("member/offers/<int:offer_id>/claim/", views.ClaimOfferView.as_view(), name="claim_offer"),
    path("member/claims/", views.MyClaimsView.as_view(), name="my_claims"),
    path("member/claims/cancel/", views.CancelClaimView.as_view(), name="cancel_claim"),
    path("merchant/claims/", views.MerchantClaimsView.as_view(), name="merchant_claims"),
    path("merchant/claims/redeem/", views.RedeemClaimView.as_view(), name="redeem_claim"),
]
