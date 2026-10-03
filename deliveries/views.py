from decimal import Decimal, InvalidOperation

from django.conf import settings as dj_settings
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.permissions import IsRole
from claims.models import OfferClaim
from core.models import Area
from riders.models import Rider

from .models import DeliveryJob, RiderEarning, SharedRoute
from .serializers import DeliveryJobSerializer, RiderEarningSerializer, SharedRouteSerializer
from .services import (
    DeliveryError,
    accept_job,
    attach_job_to_route,
    cancel_route,
    complete_route,
    confirm_delivery,
    create_route,
    mark_arrived,
    mark_failed,
    mark_on_route,
    mark_picked_up,
    publish_route,
    request_delivery,
)

IsRider = IsRole.for_roles("rider")
IsMember = IsRole.for_roles("member")


def _error(code, exc, status=400):
    message = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
    return Response({"success": False, "error": {"code": code, "message": message, "details": {}}}, status=status)


def _error_response(code, message, status=400):
    return Response({"success": False, "error": {"code": code, "message": message, "details": {}}}, status=status)


class RequestDeliveryView(APIView):
    """POST /api/v1/member/delivery/request/
    body: {claim_code, dropoff_area, dropoff_address, delivery_type}  (fare is computed server-side)
    """
    serializer_class = DeliveryJobSerializer

    permission_classes = [IsAuthenticated, IsMember]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"

    def post(self, request):
        code = request.data.get("claim_code", "")
        claim = OfferClaim.objects.filter(code=code.strip().upper(), member__user=request.user).first()
        if claim is None:
            return Response(
                {"success": False, "error": {"code": "CLAIM_NOT_FOUND", "message": "Claim not found.", "details": {}}},
                status=404,
            )
        area = Area.objects.filter(name=request.data.get("dropoff_area", "")).first()
        if area is None:
            return Response(
                {"success": False, "error": {"code": "INVALID_AREA", "message": "Unknown dropoff area.", "details": {}}},
                status=400,
            )
        delivery_type = request.data.get("delivery_type", DeliveryJob.DeliveryType.NORMAL)
        if delivery_type not in DeliveryJob.DeliveryType.values:
            return _error_response("INVALID_DELIVERY_TYPE", "Unknown delivery type.")
        address = str(request.data.get("dropoff_address", "")).strip()[:200]
        if not address:
            return _error_response("ADDRESS_REQUIRED", "Please enter a drop-off address or landmark.")
        if claim.status != OfferClaim.Status.CLAIMED or not claim.offer.delivery_available:
            return _error_response("NOT_DELIVERABLE", "This claim is not eligible for delivery.")
        # The client's "fare" field is ignored on purpose: the server computes it.
        from .services import compute_fare

        fare = compute_fare(claim.offer.merchant, area, delivery_type)

        try:
            job = request_delivery(
                claim=claim,
                merchant=claim.offer.merchant,
                dropoff_area=area,
                dropoff_address=address,
                delivery_type=delivery_type,
                fare=fare,
            )
        except DeliveryError as exc:
            return _error("DELIVERY_REQUEST_FAILED", exc)
        return Response({"success": True, "data": DeliveryJobSerializer(job).data}, status=201)


class AvailableJobsView(APIView):
    """GET /api/v1/rider/jobs/ — open jobs plus this rider's own active jobs."""
    serializer_class = DeliveryJobSerializer

    permission_classes = [IsAuthenticated, IsRider]

    def get(self, request):
        rider = get_object_or_404(Rider, user=request.user)
        jobs = DeliveryJob.objects.filter(status=DeliveryJob.Status.REQUESTED) | DeliveryJob.objects.filter(
            rider=rider, status__in=DeliveryJob.ACTIVE_STATUSES
        )
        return Response({"success": True, "data": DeliveryJobSerializer(jobs.distinct(), many=True).data})


class AcceptJobView(APIView):
    serializer_class = DeliveryJobSerializer
    permission_classes = [IsAuthenticated, IsRider]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"

    def post(self, request, job_id):
        rider = get_object_or_404(Rider, user=request.user)
        try:
            job = accept_job(rider, job_id)
        except DeliveryError as exc:
            return _error("ACCEPT_FAILED", exc)
        return Response({"success": True, "data": DeliveryJobSerializer(job).data})


class ArrivedJobView(APIView):
    serializer_class = DeliveryJobSerializer
    permission_classes = [IsAuthenticated, IsRider]

    def post(self, request, job_id):
        rider = get_object_or_404(Rider, user=request.user)
        try:
            job = mark_arrived(rider, job_id)
        except DeliveryError as exc:
            return _error("ARRIVED_FAILED", exc)
        return Response({"success": True, "data": DeliveryJobSerializer(job).data})


class PickedUpJobView(APIView):
    serializer_class = DeliveryJobSerializer
    permission_classes = [IsAuthenticated, IsRider]

    def post(self, request, job_id):
        rider = get_object_or_404(Rider, user=request.user)
        try:
            job, raw_otp = mark_picked_up(rider, job_id)
        except DeliveryError as exc:
            return _error("PICKUP_FAILED", exc)
        data = DeliveryJobSerializer(job).data
        # DEV ONLY: surface the OTP the same way accounts does for phone
        # verification, until a real SMS gateway exists (Phase 10).
        if dj_settings.DEBUG:
            data["dev_only_otp"] = raw_otp
        return Response({"success": True, "data": data})


class OnRouteJobView(APIView):
    serializer_class = DeliveryJobSerializer
    permission_classes = [IsAuthenticated, IsRider]

    def post(self, request, job_id):
        rider = get_object_or_404(Rider, user=request.user)
        try:
            job = mark_on_route(rider, job_id)
        except DeliveryError as exc:
            return _error("ON_ROUTE_FAILED", exc)
        return Response({"success": True, "data": DeliveryJobSerializer(job).data})


class DeliveredJobView(APIView):
    """POST /api/v1/rider/jobs/<id>/delivered/  body: {"otp": "1234"}"""
    serializer_class = DeliveryJobSerializer

    permission_classes = [IsAuthenticated, IsRider]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "delivery_otp"

    def post(self, request, job_id):
        rider = get_object_or_404(Rider, user=request.user)
        try:
            job = confirm_delivery(rider, job_id, request.data.get("otp", ""))
        except DeliveryError as exc:
            return _error("DELIVERY_CONFIRM_FAILED", exc)
        return Response({"success": True, "data": DeliveryJobSerializer(job).data})


class FailedJobView(APIView):
    """POST /api/v1/rider/jobs/<id>/failed/  body: {"reason": "..."}"""
    serializer_class = DeliveryJobSerializer

    permission_classes = [IsAuthenticated, IsRider]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"

    def post(self, request, job_id):
        rider = get_object_or_404(Rider, user=request.user)
        try:
            job = mark_failed(rider, job_id, request.data.get("reason", ""))
        except DeliveryError as exc:
            return _error("MARK_FAILED_ERROR", exc)
        return Response({"success": True, "data": DeliveryJobSerializer(job).data})


class RiderEarningsView(APIView):
    """GET /api/v1/rider/earnings/"""
    serializer_class = RiderEarningSerializer

    permission_classes = [IsAuthenticated, IsRider]

    def get(self, request):
        rider = get_object_or_404(Rider, user=request.user)
        earnings = RiderEarning.objects.filter(rider=rider)
        totals = earnings.aggregate(
            gross=Sum("gross_amount"), commission=Sum("commission_amount"), net=Sum("net_amount")
        )
        return Response(
            {
                "success": True,
                "data": {
                    "totals": {k: (v or 0) for k, v in totals.items()},
                    "records": RiderEarningSerializer(earnings, many=True).data,
                },
            }
        )


class RiderRoutesView(APIView):
    """GET/POST /api/v1/rider/routes/"""

    permission_classes = [IsAuthenticated, IsRider]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "write"
    serializer_class = SharedRouteSerializer

    def get(self, request):
        rider = get_object_or_404(Rider, user=request.user)
        routes = SharedRoute.objects.filter(rider=rider)
        return Response({"success": True, "data": SharedRouteSerializer(routes, many=True).data})

    def post(self, request):
        from django.utils.dateparse import parse_datetime

        rider = get_object_or_404(Rider, user=request.user)
        origin = Area.objects.filter(pk=request.data.get("origin_area_id")).first()
        destination = Area.objects.filter(pk=request.data.get("destination_area_id")).first()
        departure_time = parse_datetime(request.data.get("departure_time", "")) if request.data.get("departure_time") else None
        if not origin or not destination or not departure_time:
            return Response(
                {"success": False, "error": {"code": "INVALID_INPUT", "message": "origin_area_id, destination_area_id and departure_time are required.", "details": {}}},
                status=400,
            )
        try:
            route = create_route(
                rider, origin, destination, departure_time, int(request.data.get("max_packages", 5))
            )
        except DeliveryError as exc:
            return _error("ROUTE_CREATE_FAILED", exc)
        return Response({"success": True, "data": SharedRouteSerializer(route).data}, status=201)


class PublishRouteView(APIView):
    permission_classes = [IsAuthenticated, IsRider]
    serializer_class = SharedRouteSerializer

    def post(self, request, route_id):
        rider = get_object_or_404(Rider, user=request.user)
        try:
            route = publish_route(rider, route_id)
        except DeliveryError as exc:
            return _error("PUBLISH_FAILED", exc)
        return Response({"success": True, "data": SharedRouteSerializer(route).data})


class AttachJobToRouteView(APIView):
    permission_classes = [IsAuthenticated, IsRider]
    serializer_class = DeliveryJobSerializer

    def post(self, request, route_id, job_id):
        rider = get_object_or_404(Rider, user=request.user)
        try:
            job = attach_job_to_route(rider, route_id, job_id)
        except DeliveryError as exc:
            return _error("ATTACH_FAILED", exc)
        return Response({"success": True, "data": DeliveryJobSerializer(job).data})


class CompleteRouteView(APIView):
    permission_classes = [IsAuthenticated, IsRider]
    serializer_class = SharedRouteSerializer

    def post(self, request, route_id):
        rider = get_object_or_404(Rider, user=request.user)
        try:
            route = complete_route(rider, route_id)
        except DeliveryError as exc:
            return _error("COMPLETE_FAILED", exc)
        return Response({"success": True, "data": SharedRouteSerializer(route).data})


class CancelRouteView(APIView):
    permission_classes = [IsAuthenticated, IsRider]
    serializer_class = SharedRouteSerializer

    def post(self, request, route_id):
        rider = get_object_or_404(Rider, user=request.user)
        try:
            route = cancel_route(rider, route_id)
        except DeliveryError as exc:
            return _error("CANCEL_FAILED", exc)
        return Response({"success": True, "data": SharedRouteSerializer(route).data})
