from django.urls import path

from . import views

app_name = "members"

urlpatterns = [
    path("member/referrals/", views.MyReferralsView.as_view(), name="my_referrals"),
]
