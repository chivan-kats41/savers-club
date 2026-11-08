from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("notifications/", views.MyNotificationsView.as_view(), name="my_notifications"),
    path("notifications/<int:notification_id>/read/", views.MarkNotificationReadView.as_view(), name="mark_read"),
    path("notifications/preferences/", views.NotificationPreferencesView.as_view(), name="preferences"),
    path("push/", views.PushStatusView.as_view(), name="push_status"),
    path("push/subscribe/", views.PushSubscribeView.as_view(), name="push_subscribe"),
    path("push/unsubscribe/", views.PushUnsubscribeView.as_view(), name="push_unsubscribe"),
    path("push/test/", views.PushTestView.as_view(), name="push_test"),
]
