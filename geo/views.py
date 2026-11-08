"""JSON API for the geo features. Same envelope as the rest of the API: {"success": bool, "data"|"error": ...}.

Privacy notes
-------------
* ``nearby-deals`` takes coordinates as a transient query: they are used to rank deals and are never stored.
* Position is only stored for users who opted in (see geo.services.history), and only the owner can read or delete it.
* A rider's live position is only recorded during an active delivery and only the customer of that job can see it.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.permissions import IsRole
from core.middleware import get_client_ip
from core.models import Area, AuditLog
from core.services import get_setting_decimal
from deliveries.models import DeliveryJob
from deliveries.services import open_jobs_for_riders
from merchants.models import Merchant
from riders.models import Rider

from .models import LocationHistory
from .services import geocoding, history, nearby, routing
from .utils import area_point, dec6, distance_label, haversine_km, in_uganda, merchant_point, valid_coords

IsMerchant = IsRole.for_roles("merchant")
IsRider = IsRole.for_roles("rider")
IsMember = IsRole.for_roles("member")

ACTIVE_RIDER_STATUSES = [
    DeliveryJob.Status.ACCEPTED, DeliveryJob.Status.ARRIVED_AT_SELLER, DeliveryJob.Status.PICKED_UP,
    DeliveryJob.Status.ON_ROUTE,
]
TO_PICKUP = [DeliveryJob.Status.REQUESTED, DeliveryJob.Status.ASSIGNED, DeliveryJob.Status.ACCEPTED,
             DeliveryJob.Status.ARRIVED_AT_SELLER]
TO_DROPOFF = [DeliveryJob.Status.PICKED_UP, DeliveryJob.Status.ON_ROUTE]
HANDOVER_BUFFER_MIN = 5   # time at the seller before the rider sets off


def ok(data=None, status=200):
    return Response({"success": True, "data": data if data is not None else {}}, status=status)


def fail(code, message, status=400):
    return Response({"success": False, "error": {"code": code, "message": message, "details": {}}}, status=status)


class Scoped(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "geo_read"


# --------------------------------------------------------------------------- nearby deals --

class NearbyDealsView(Scoped):
    """GET /api/v1/geo/nearby-deals/?lat=&lng=&limit=&radius=  — public (the landing page is public)."""
    permission_classes = [AllowAny]

    def get(self, request):
        from hub import selectors

        try:
            limit = max(1, min(int(request.query_params.get("limit", 9)), 24))
        except ValueError:
            limit = 9
        try:
            radius = float(request.query_params.get("radius") or 0) or None
        except ValueError:
            radius = None
        if radius is not None:
            radius = max(0.5, min(radius, 50.0))
        origin = nearby.resolve_origin(request.user, request.query_params.get("lat"), request.query_params.get("lng"))
        deals = selectors.hot_deals_near(origin, limit=limit, radius=radius)
        return ok({
            "origin": origin.as_dict() if origin else None,
            "radius_km": radius or nearby.default_radius_km(),
            "deals": [selectors.deal_json(d) for d in deals],
        })


# --------------------------------------------------------------------------- geocoding / routes --

class GeocodeView(APIView):
    """GET /api/v1/geo/geocode/?q=kireka+market"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "geocode"

    def get(self, request):
        return ok(geocoding.search(request.query_params.get("q", "")))


class ReverseGeocodeView(APIView):
    """GET /api/v1/geo/reverse/?lat=&lng="""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "geocode"

    def get(self, request):
        result = geocoding.reverse(request.query_params.get("lat"), request.query_params.get("lng"))
        if not result.get("valid"):
            return fail("INVALID_LOCATION", "That point is not a valid location in Uganda.")
        return ok(result)


class RouteView(APIView):
    """GET /api/v1/geo/route/?from_lat=&from_lng=&to_lat=&to_lng="""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "route"

    def get(self, request):
        q = request.query_params
        a = valid_coords(q.get("from_lat"), q.get("from_lng"))
        b = valid_coords(q.get("to_lat"), q.get("to_lng"))
        if a is None or b is None or not in_uganda(*a) or not in_uganda(*b):
            return fail("INVALID_LOCATION", "Both points must be valid locations in Uganda.")
        return ok(routing.route(a, b))


# --------------------------------------------------------------------------- my location --

def _state_payload(user):
    state = history.get_state(user)
    origin = nearby.resolve_origin(user)
    return {
        "share_location": state.share_location,
        "save_history": state.save_history,
        "area_override": {"id": state.area_override_id, "name": state.area_override.name} if state.area_override_id else None,
        "last_fix": {
            "lat": float(state.latitude), "lng": float(state.longitude), "accuracy_m": state.accuracy_m,
            "area": state.area.name if state.area else None, "at": state.located_at.isoformat(),
        } if state.latitude is not None and state.located_at else None,
        "origin": origin.as_dict() if origin else None,
        "retention_days": history.history_retention_days(),
    }


class MyLocationView(Scoped):
    """GET/PATCH /api/v1/geo/me/  — consent switches and the manual 'I'm in <area>' choice."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return ok(_state_payload(request.user))

    def patch(self, request):
        data = request.data
        kwargs = {}
        for key in ("share_location", "save_history"):
            if key in data:
                v = data[key]
                if not isinstance(v, bool):
                    v = str(v).strip().lower() in ("1", "true", "yes", "on")
                kwargs[key] = v
        if "area_override" in data:
            raw = data["area_override"]
            if raw in (None, "", 0, "0"):
                kwargs["area_override"] = None
            else:
                area = Area.objects.filter(pk=raw, is_active=True).first() if str(raw).isdigit() else None
                if area is None:
                    return fail("INVALID_AREA", "Unknown area.")
                kwargs["area_override"] = area
        history.update_settings(request.user, **kwargs)
        return ok(_state_payload(request.user))

    put = patch


class LocationPingView(APIView):
    """POST /api/v1/geo/me/ping/ {lat, lng, accuracy}  — the device reports where it is.

    Stored only if the user switched sharing on; otherwise the answer still carries the nearest area (so the page can
    say "Near Kireka") but nothing is kept."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "geo_write"

    def post(self, request):
        try:
            result = history.record_fix(
                request.user, request.data.get("lat"), request.data.get("lng"), request.data.get("accuracy"),
                label=request.data.get("label", ""))
        except ValidationError as exc:
            return fail("INVALID_LOCATION", "; ".join(exc.messages))
        area = result["area"]
        return ok({"area": area.name if area else None, "stored": result["stored"], "history": result["history"]})


def _history_row(h):
    return {"id": h.pk, "lat": float(h.latitude), "lng": float(h.longitude), "area": h.area.name if h.area else None,
            "label": h.place_label, "source": h.source, "source_label": h.get_source_display(),
            "at": h.created_at.isoformat()}


class LocationHistoryView(Scoped):
    """GET /api/v1/geo/me/history/  ·  DELETE (clear everything)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = LocationHistory.objects.filter(user=request.user).exclude(
            source=LocationHistory.Source.RIDER_LIVE).select_related("area")[:100]
        return ok({"history": [_history_row(h) for h in rows], "retention_days": history.history_retention_days()})

    def delete(self, request):
        return ok({"deleted": history.clear_history(request.user)})


class LocationHistoryItemView(Scoped):
    permission_classes = [IsAuthenticated]

    def delete(self, request, entry_id):
        row = get_object_or_404(LocationHistory, pk=entry_id, user=request.user)
        row.delete()
        return ok({"deleted": 1})


class LocationExportView(Scoped):
    """GET /api/v1/geo/me/history/export/  — everything we hold about the user's locations, as JSON."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = LocationHistory.objects.filter(user=request.user).select_related("area")
        return ok({"state": _state_payload(request.user), "history": [_history_row(h) for h in rows]})


# --------------------------------------------------------------------------- merchant pin --

class MerchantLocationView(APIView):
    """POST /api/v1/merchant/location/ {lat, lng, address?}  — pin the shop on the map."""
    permission_classes = [IsAuthenticated, IsMerchant]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "geo_write"

    def post(self, request):
        merchant = get_object_or_404(Merchant.objects.select_related("area"), user=request.user)
        pt = valid_coords(request.data.get("lat"), request.data.get("lng"))
        if pt is None or not in_uganda(*pt):
            return fail("INVALID_LOCATION", "Drop the pin on a valid location in Uganda.")
        centre = area_point(merchant.area)
        limit_km = float(get_setting_decimal("geo.merchant_max_km_from_area", Decimal("15")))
        if centre is not None:
            km = haversine_km(pt[0], pt[1], centre[0], centre[1])
            if km > limit_km:
                return fail("OUTSIDE_AREA",
                            f"That pin is {km:.0f} km from {merchant.area.name}. Move it closer, or ask support to change your area.")
        merchant.latitude, merchant.longitude = dec6(pt[0]), dec6(pt[1])
        fields = ["latitude", "longitude", "updated_at"]
        address = str(request.data.get("address") or "").strip()[:255]
        if address:
            merchant.address = address
            fields.append("address")
        merchant.save(update_fields=fields)
        AuditLog.objects.create(
            actor=request.user, action="merchant_location_set", object_type="merchant", object_id=str(merchant.pk),
            ip_address=get_client_ip(request), request_id=getattr(request, "request_id", ""),
            metadata={"lat": pt[0], "lng": pt[1]})
        return ok({"lat": pt[0], "lng": pt[1], "address": merchant.address})


# --------------------------------------------------------------------------- delivery tracking --

def _job_points(job, exact_dropoff=True):
    pickup = merchant_point(job.pickup_merchant)
    if job.dropoff_latitude is not None and job.dropoff_longitude is not None and exact_dropoff:
        drop = (float(job.dropoff_latitude), float(job.dropoff_longitude), True)
    else:
        ap = area_point(job.dropoff_area)
        drop = (ap[0], ap[1], False) if ap else None
    return pickup, drop


def _point(pt, label=""):
    return {"lat": pt[0], "lng": pt[1], "precise": pt[2], "label": label} if pt else None


def _trip(job, rider_pt, pickup, drop):
    """Leg + ETA for the current stage of a delivery. rider_pt is (lat, lng) or None."""
    out = {"leg": "none", "route": None, "eta_minutes": None, "eta_at": None}
    if job.status in TO_PICKUP and pickup and drop:
        out["leg"] = "to_pickup"
        second = routing.route(pickup[:2], drop[:2])
        if rider_pt and job.status != DeliveryJob.Status.REQUESTED:
            first = routing.route(rider_pt, pickup[:2])
            out["route"] = first
            total = first["duration_min"] + HANDOVER_BUFFER_MIN + second["duration_min"]
        else:
            out["route"] = second          # no rider yet: show the shop -> drop-off trip
            out["leg"] = "trip"
            total = None
        if total is not None:
            out["eta_minutes"] = total
    elif job.status in TO_DROPOFF and drop:
        out["leg"] = "to_dropoff"
        start = rider_pt or (pickup[:2] if pickup else None)
        if start:
            out["route"] = routing.route(start, drop[:2])
            out["eta_minutes"] = out["route"]["duration_min"]
    if out["eta_minutes"] is not None:
        out["eta_at"] = (timezone.now() + timedelta(minutes=out["eta_minutes"])).isoformat()
    return out


class MemberDeliveryTrackView(Scoped):
    """GET /api/v1/member/delivery/<id>/track/ — the customer follows their own delivery."""
    permission_classes = [IsAuthenticated, IsMember]

    def get(self, request, job_id):
        job = get_object_or_404(
            DeliveryJob.objects.select_related("pickup_merchant", "pickup_merchant__area", "dropoff_area"),
            pk=job_id, claim__member__user=request.user)
        pickup, drop = _job_points(job)
        rider_pt, rider = None, None
        if job.rider_id and job.status in ACTIVE_RIDER_STATUSES:
            fix = history.latest_rider_fix(job)
            if fix is not None:
                rider_pt = (float(fix.latitude), float(fix.longitude))
                rider = {"lat": rider_pt[0], "lng": rider_pt[1], "at": fix.created_at.isoformat(),
                         "age_s": int((timezone.now() - fix.created_at).total_seconds())}
        data = {
            "job": {"id": job.pk, "status": job.status, "status_label": job.get_status_display(),
                    "dropoff_address": job.dropoff_address},
            "pickup": _point(pickup, job.pickup_merchant.business_name),
            "dropoff": _point(drop, job.dropoff_address),
            "rider": rider,
            "live": job.status in ACTIVE_RIDER_STATUSES,
        }
        data.update(_trip(job, rider_pt, pickup, drop) if job.status in TO_PICKUP + TO_DROPOFF else
                    {"leg": "none", "route": None, "eta_minutes": None, "eta_at": None})
        return ok(data)


# --------------------------------------------------------------------------- rider --

class RiderLocationView(APIView):
    """POST /api/v1/rider/location/ {lat, lng, accuracy}

    Recorded only while the rider has an active delivery (nothing is kept otherwise). When a loaded rider gets within
    about a kilometre of the drop-off the customer is told, once."""
    permission_classes = [IsAuthenticated, IsRider]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "rider_ping"

    def post(self, request):
        rider = get_object_or_404(Rider, user=request.user)
        pt = valid_coords(request.data.get("lat"), request.data.get("lng"))
        if pt is None or not in_uganda(*pt):
            return fail("INVALID_LOCATION", "Invalid location.")
        job = (DeliveryJob.objects.select_related("claim__member__user", "dropoff_area")
               .filter(rider=rider, status__in=ACTIVE_RIDER_STATUSES).order_by("-assigned_at", "-id").first())
        if job is None:
            return ok({"tracking": False})
        try:
            history.record_rider_fix(request.user, job, pt[0], pt[1], request.data.get("accuracy"))
        except ValidationError as exc:
            return fail("INVALID_LOCATION", "; ".join(exc.messages))

        if job.status in TO_DROPOFF and job.claim_id:
            _, drop = _job_points(job)
            if drop:
                km = haversine_km(pt[0], pt[1], drop[0], drop[1])
                if km <= 1.0 and cache.add(f"rider-near:{job.pk}", 1, timeout=6 * 3600):
                    from notifications.services.dispatch import notify

                    minutes = routing.estimate(pt, drop[:2])["duration_min"]
                    notify(job.claim.member.user, "delivery", "Your rider is nearby",
                           f"Your rider is about {minutes} min away. Keep your phone close.",
                           metadata={"job_id": job.pk, "url": "/member/#delivery", "_channels": ["in_app", "push"]})
        return ok({"tracking": True, "job_id": job.pk})


class RiderJobNavView(Scoped):
    """GET /api/v1/rider/jobs/<id>/nav/?lat=&lng= — pickup, drop-off, route and ETA for a rider's job.

    Open (not yet accepted) jobs only reveal the drop-off *area*; the exact point is for the rider who accepted it."""
    permission_classes = [IsAuthenticated, IsRider]

    def get(self, request, job_id):
        rider = get_object_or_404(Rider, user=request.user)
        qs = DeliveryJob.objects.select_related("pickup_merchant", "pickup_merchant__area", "dropoff_area")
        job = qs.filter(pk=job_id, rider=rider).first()
        owned = job is not None
        if job is None:
            job = get_object_or_404(qs.filter(pk__in=open_jobs_for_riders().values("pk")), pk=job_id)
        pickup, drop = _job_points(job, exact_dropoff=owned)
        start = valid_coords(request.query_params.get("lat"), request.query_params.get("lng"))
        if start is None:
            fix = history.latest_rider_fix(job) if owned else None
            start = (float(fix.latitude), float(fix.longitude)) if fix else None
        trip = _trip(job, start, pickup, drop) if job.status in TO_PICKUP + TO_DROPOFF else {
            "leg": "none", "route": None, "eta_minutes": None, "eta_at": None}
        return ok({"job": {"id": job.pk, "status": job.status, "dropoff_address": job.dropoff_address if owned else ""},
                   "pickup": _point(pickup, job.pickup_merchant.business_name),
                   "dropoff": _point(drop, job.dropoff_address if owned else job.dropoff_area.name),
                   "owned": owned, **trip})
