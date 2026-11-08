from django.urls import path

from . import views

app_name = "accounts_api"

urlpatterns = [
    path("admin/users/<uuid:user_id>/suspend/", views.SuspendUserView.as_view(), name="suspend_user"),
    path("admin/users/<uuid:user_id>/reactivate/", views.ReactivateUserView.as_view(), name="reactivate_user"),
]
