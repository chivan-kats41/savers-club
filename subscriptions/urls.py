from django.urls import path

from . import views

app_name = "subscriptions"

urlpatterns = [
    path("member/subscription/", views.MySubscriptionView.as_view(), name="my_subscription"),
    path("member/subscription/renew/", views.RenewSubscriptionView.as_view(), name="renew"),
    path("member/subscription/pause/", views.PauseSubscriptionView.as_view(), name="pause"),
]
