from django.urls import path

from . import views

app_name = "offers"

urlpatterns = [
    path("merchant/offers/", views.MerchantOffersView.as_view(), name="merchant_offers"),
    path("merchant/offers/<int:offer_id>/", views.MerchantOfferDetailView.as_view(), name="merchant_offer_detail"),
    path("merchant/offers/<int:offer_id>/pause/", views.PauseOfferView.as_view(), name="pause_offer"),
    path("offers/categories/", views.OfferCategoriesView.as_view(), name="categories"),
    path("member/offers/nearby/", views.NearbyOffersView.as_view(), name="nearby_offers"),
]
