from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationPreferenceSerializer, NotificationSerializer
from .services.dispatch import get_or_create_preferences


class MyNotificationsView(APIView):
    """GET /api/v1/notifications/ — own notifications, any role."""
    serializer_class = NotificationSerializer

    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(user=request.user)
        return Response({"success": True, "data": NotificationSerializer(notifications, many=True).data})


class MarkNotificationReadView(APIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, notification_id):
        notification = get_object_or_404(Notification, pk=notification_id, user=request.user)
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response({"success": True, "data": NotificationSerializer(notification).data})


class NotificationPreferencesView(APIView):
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        prefs = get_or_create_preferences(request.user)
        return Response({"success": True, "data": NotificationPreferenceSerializer(prefs).data})

    def patch(self, request):
        prefs = get_or_create_preferences(request.user)
        serializer = NotificationPreferenceSerializer(prefs, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True, "data": serializer.data})


# ----------------------------------------------------------------------------- Web Push --

from django.conf import settings as _settings  # noqa: E402
from rest_framework.throttling import ScopedRateThrottle  # noqa: E402

from .models import PushSubscription  # noqa: E402
from .services.push import endpoint_is_allowed, push_configured, send_push  # noqa: E402


def _push_error(code, message, status=400):
    return Response({"success": False, "error": {"code": code, "message": message, "details": {}}}, status=status)


class PushStatusView(APIView):
    """GET /api/v1/push/ — is push available, and how many devices does this user have?"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"success": True, "data": {
            "configured": push_configured(),
            "public_key": _settings.VAPID_PUBLIC_KEY if push_configured() else "",
            "devices": PushSubscription.objects.filter(user=request.user).count(),
        }})


class PushSubscribeView(APIView):
    """POST /api/v1/push/subscribe/ {endpoint, keys: {p256dh, auth}}  — register this browser/device."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "push"

    def post(self, request):
        if not push_configured():
            return _push_error("PUSH_NOT_CONFIGURED", "Push notifications are not switched on for this site yet.", 503)
        data = request.data if isinstance(request.data, dict) else {}
        endpoint = str(data.get("endpoint") or "")
        keys = data.get("keys") if isinstance(data.get("keys"), dict) else {}
        p256dh, auth = str(keys.get("p256dh") or ""), str(keys.get("auth") or "")
        if not endpoint or len(endpoint) > 500 or not p256dh or not auth or len(p256dh) > 255 or len(auth) > 255:
            return _push_error("INVALID_SUBSCRIPTION", "That push subscription is not valid.")
        if not endpoint_is_allowed(endpoint):
            return _push_error("INVALID_SUBSCRIPTION", "That push service is not supported.")
        PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={"user": request.user, "p256dh": p256dh, "auth": auth,
                      "user_agent": request.headers.get("User-Agent", "")[:255], "failure_count": 0},
        )
        return Response({"success": True, "data": {"devices": PushSubscription.objects.filter(user=request.user).count()}}, status=201)


class PushUnsubscribeView(APIView):
    """POST /api/v1/push/unsubscribe/ {endpoint}  — forget this device (or all with {"all": true})."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "push"

    def post(self, request):
        qs = PushSubscription.objects.filter(user=request.user)
        if not (isinstance(request.data, dict) and request.data.get("all") is True):
            qs = qs.filter(endpoint=str(request.data.get("endpoint") or ""))
        deleted, _ = qs.delete()
        return Response({"success": True, "data": {"removed": deleted}})


class PushTestView(APIView):
    """POST /api/v1/push/test/ — send a test notification to my own devices."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "push"

    def post(self, request):
        if not push_configured():
            return _push_error("PUSH_NOT_CONFIGURED", "Push notifications are not switched on for this site yet.", 503)
        sent = send_push(request.user, "1K Saver Club", "Push notifications are working on this device.",
                         url="/notifications/", tag="test")
        if not sent:
            return _push_error("NO_DEVICE", "No subscribed device accepted the test. Enable alerts on this device first.")
        return Response({"success": True, "data": {"sent": sent}})
