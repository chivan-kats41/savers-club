from notifications.models import Notification


def unread_notifications(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"unread_count": Notification.objects.filter(user=user, is_read=False).count()}
