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
