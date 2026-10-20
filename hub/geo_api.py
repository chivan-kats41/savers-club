"""Location endpoints. Every write is CSRF-protected, rate limited, validated (finite numbers, real ranges, GPS accuracy,
impossible jumps) and returns only the caller's OWN rounded location. Nobody can read anyone else's coordinates here."""
import logging

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated

from core import geo, geoservice
from core.models import Area
from members.models import Member
from merchants.models import Merchant
from riders.models import Rider

from .api import AdminView, Throttled, audit, fail, ok, to_decimal, to_int

logger = logging.getLogger("security")

PROFILES = {"member": Member, "rider": Rider, "merchant": Merchant}


def _profile(request, role):
    model = PROFILES.get(role)
    if model is None:
        return None, fail("INVALID_ROLE", "Unknown role.", 400)
    profile = model.objects.filter(user=request.user).select_related("area").first() if role != "rider" else model.objects.filter(user=request.user).first()
    if profile is None or not request.user.has_role(role):
        return None, fail("NO_PROFILE", f"You don't have a {role} profile.", 403)
    return profile, None


def _risk(user, kind, **meta):
    try:
        from core.services import record_risk_event

        record_risk_event(kind, user=user, metadata=meta)
    except Exception:
        logger.exception("could not record risk event %s", kind)


class LocationView(Throttled):
    """POST /api/v1/geo/location/ {role, lat, lng, accuracy?}"""
    permission_classes = [IsAuthenticated]
    throttle_scope = "location"

    def post(self, request):
        role = request.data.get("role", "member")
        profile, err = _profile(request, role)
        if err:
            return err
        try:
            lat, lng = geo.valid_point(request.data.get("lat"), request.data.get("lng"))
        except ValueError as exc:
            return fail("INVALID_LOCATION", str(exc))
        gs = geoservice.geo_settings()
        acc = to_decimal(request.data.get("accuracy")) if request.data.get("accuracy") not in (None, "") else None
        if acc is not None and acc > gs.max_accuracy_m:
            return fail("LOW_ACCURACY", f"Your device's location is only accurate to about {int(acc)} m. "
                        "Move to open sky or switch on precise location, or pick your area instead.")

        if role == "member":
            prev = geoservice.member_point(profile)
            if geoservice.implausible_jump(prev, lat, lng):
                _risk(request.user, "location_jump", role=role)     # accept (VPNs, flights) but leave a trail
            prev, moved = geoservice.set_member_location(profile, lat, lng, "gps")
            p = geoservice.member_point(profile)
        elif role == "rider":
            prev = geoservice.rider_point(profile, gs, fresh_only=False)
            if geoservice.implausible_jump(prev, lat, lng):
                _risk(request.user, "location_jump", role=role)
                return fail("LOCATION_JUMP", "That location doesn't fit your last position. Check your GPS and try again.")
            prev, moved = geoservice.set_rider_location(profile, lat, lng)
            p = geoservice.rider_point(profile, gs, fresh_only=False)
        else:
            geoservice.set_merchant_location(profile, lat, lng)
            audit(request, "merchant_location_set", profile)
            prev, moved = None, None
            p = geoservice.merchant_point(profile)
        return ok({"role": role, "lat": p.lat, "lng": p.lng, "source": p.source,
                   "moved_km": None if moved is None else round(moved, 2),
                   "changed": moved is None or moved >= 0.3})


class AreaLocationView(Throttled):
    """POST /api/v1/geo/area/ {area_id}: "I'll use this area instead of GPS"."""
    permission_classes = [IsAuthenticated]
    throttle_scope = "location"

    def post(self, request):
        member, err = _profile(request, "member")
        if err:
            return err
        area = Area.objects.filter(pk=to_int(request.data.get("area_id")), is_active=True).first()
        if area is None:
            return fail("INVALID", "Choose an area from the list.")
        try:
            geoservice.set_member_area_location(member, area)
        except ValueError as exc:
            return fail("AREA_UNMAPPED", str(exc))
        return ok({"role": "member", "source": "area", "area": area.name, "changed": True})


class RadiusView(Throttled):
    """POST /api/v1/geo/radius/ {radius_km}"""
    permission_classes = [IsAuthenticated]
    throttle_scope = "location"

    def post(self, request):
        member, err = _profile(request, "member")
        if err:
            return err
        gs = geoservice.geo_settings()
        km = to_int(request.data.get("radius_km"))
        if km not in gs.radius_choices:
            return fail("INVALID", f"Choose one of: {', '.join(str(c) for c in gs.radius_choices)} km.")
        member.search_radius_km = km
        member.save(update_fields=["search_radius_km"])
        return ok({"radius_km": km, "changed": True})


class ClearLocationView(Throttled):
    """POST /api/v1/geo/clear/ {role}: stop sharing, wipe the stored point."""
    permission_classes = [IsAuthenticated]
    throttle_scope = "location"

    def post(self, request):
        profile, err = _profile(request, request.data.get("role", "member"))
        if err:
            return err
        geoservice.clear_location(profile)
        return ok({"cleared": True, "changed": True})


class AdminAreaCoordinatesView(AdminView):
    """PATCH /api/v1/admin/areas/<id>/ {latitude, longitude}: correct where an area is on the map."""
    required = "content_manage"

    def patch(self, request, area_id):
        area = get_object_or_404(Area, pk=area_id)
        try:
            lat, lng = geo.valid_point(request.data.get("latitude"), request.data.get("longitude"))
        except ValueError as exc:
            return fail("INVALID_LOCATION", str(exc))
        old = [str(area.latitude), str(area.longitude)]
        area.latitude, area.longitude = round(lat, 6), round(lng, 6)
        area.save(update_fields=["latitude", "longitude"])
        audit(request, "area_coordinates_changed", area, old=old, new=[str(area.latitude), str(area.longitude)])
        return ok({"id": area.pk, "latitude": float(area.latitude), "longitude": float(area.longitude)})
