from django.urls import path

from . import views

app_name = "savings"

urlpatterns = [
    path("member/savings/", views.MySavingsView.as_view(), name="my_savings"),
    path("member/savings/history/", views.MySavingsHistoryView.as_view(), name="my_savings_history"),
]
