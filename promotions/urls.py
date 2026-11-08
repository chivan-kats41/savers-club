from django.urls import path

from . import views

app_name = "promotions"

urlpatterns = [
    path("promotions/packages/", views.PromotionPackagesView.as_view(), name="packages"),
    path("merchant/promotions/", views.MyPromotionsView.as_view(), name="my_promotions"),
    path("merchant/promotions/purchase/", views.PurchasePromotionView.as_view(), name="purchase_promotion"),
]
