"""Geo-locking: show (and allow) only what is near the person.

Who has a location, and how it gets there
  member   GPS from their browser/phone, or the centre of an area they pick. Latest point only, rounded to ~110 m.
  merchant shop location set once, at the shop, from the device. Falls back to the area centre (marked approximate).
  rider    live location while their page is open (latest point only, ~11 m). Must be fresh to accept jobs.

What it enforces (all on the SERVER, so the browser can't skip it)
  * members only see offers within their radius (default 5 km; the offer's own reach can shrink it)
  * members can only claim what they can see
  * riders only see / accept delivery jobs whose pickup is within the rider job radius of them
  * members see how many riders are near, never where they are

Settings (Admin console > Settings > System settings, all optional): geo.enforce, geo.default_radius_km, geo.max_radius_km,
geo.rider_job_radius_km, geo.rider_location_max_age_minutes, geo.claim_location_max_age_minutes, geo.max_accuracy_m.
"""
import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models.functions import Coalesce
from django.utils import timezone

from . import geo
from .models import SystemSetting

logger = logging.getLogger("security")

RADIUS_CHOICES = (1, 2, 5, 10, 25)
MEMBER_PLACES, RIDER_PLACES, MERCHANT_PLACES = 3, 4, 5      # ~110 m, ~11 m, ~1 m


@dataclass(frozen=True)
class GeoSettings:
    enforce: bool = True
    default_radius_km: float = 5.0
    max_radius_km: float = 25.0
    rider_job_radius_km: float = 5.0
    rider_max_age_min: int = 10
    claim_max_age_min: int = 60
    max_accuracy_m: int = 5000

    @property
    def radius_choices(self):
        return tuple(r for r in RADIUS_CHOICES if r <= self.max_radius_km) or (int(self.default_radius_km),)


def _num(raw, default, cast=float, lo=None, hi=None):
    try:
        v = cast(Decimal(str(raw).strip()))
    except Exception:
        return default
    if lo is not None and v < lo:
        return default
    if hi is not None and v > hi:
        return default
    return v


def geo_settings() -> GeoSettings:
    rows = dict(SystemSetting.objects.filter(key__startswith="geo.", is_active=True).values_list("key", "value"))
    d = GeoSettings()
    return GeoSettings(
        enforce=str(rows.get("geo.enforce", str(getattr(settings, "GEO_ENFORCE_DEFAULT", True)))).strip().lower() not in ("0", "false", "no", "off"),
        default_radius_km=_num(rows.get("geo.default_radius_km", d.default_radius_km), d.default_radius_km, lo=0.5, hi=100),
        max_radius_km=_num(rows.get("geo.max_radius_km", d.max_radius_km), d.max_radius_km, lo=1, hi=200),
        rider_job_radius_km=_num(rows.get("geo.rider_job_radius_km", d.rider_job_radius_km), d.rider_job_radius_km, lo=0.5, hi=100),
        rider_max_age_min=_num(rows.get("geo.rider_location_max_age_minutes", d.rider_max_age_min), d.rider_max_age_min, int, 1, 1440),
        claim_max_age_min=_num(rows.get("geo.claim_location_max_age_minutes", d.claim_max_age_min), d.claim_max_age_min, int, 1, 10080),
        max_accuracy_m=_num(rows.get("geo.max_accuracy_m", d.max_accuracy_m), d.max_accuracy_m, int, 10, 100000),
    )


@dataclass(frozen=True)
class Point:
    lat: float
    lng: float
    source: str = "gps"            # gps | area
    updated_at: object = None
    approx: bool = False           # True when it is only an area centre

    def km_to(self, other: "Point") -> float:
        return geo.haversine_km(self.lat, self.lng, other.lat, other.lng)


def _pt(lat, lng, source="gps", updated_at=None, approx=False):
    if lat is None or lng is None:
        return None
    return Point(float(lat), float(lng), source, updated_at, approx)


def _area_point(area):
    return _pt(area.latitude, area.longitude, "area", None, True) if area is not None else None


# ------------------------------------------------------------------------------------------ whose point is it
def member_point(member):
    return _pt(member.latitude, member.longitude, member.location_source or "gps", member.location_updated_at,
               (member.location_source == "area"))


def merchant_point(merchant):
    return _pt(merchant.latitude, merchant.longitude, merchant.location_source or "gps", merchant.location_updated_at,
               False) or _area_point(merchant.area)


def offer_point(offer):
    return merchant_point(offer.merchant) or _area_point(offer.area)


def rider_point(rider, gs=None, fresh_only=True):
    p = _pt(rider.latitude, rider.longitude, "gps", rider.location_updated_at)
    if p is None:
        return None
    if fresh_only:
        gs = gs or geo_settings()
        if rider.location_updated_at is None or rider.location_updated_at < timezone.now() - timedelta(minutes=gs.rider_max_age_min):
            return None
    return p


def member_radius_km(member, gs=None) -> float:
    gs = gs or geo_settings()
    r = float(member.search_radius_km) if member.search_radius_km else gs.default_radius_km
    return min(r, gs.max_radius_km)


# --------------------------------------------------------------------------------------------- writing points
def _moved(prev, new_lat, new_lng):
    return None if prev is None else geo.haversine_km(prev.lat, prev.lng, new_lat, new_lng)


def set_member_location(member, lat, lng, source="gps"):
    lat, lng = geo.valid_point(lat, lng)
    prev = member_point(member)
    moved = _moved(prev, lat, lng)
    member.latitude = geo.round_coord(lat, MEMBER_PLACES)
    member.longitude = geo.round_coord(lng, MEMBER_PLACES)
    member.location_source = source
    member.location_updated_at = timezone.now()
    member.save(update_fields=["latitude", "longitude", "location_source", "location_updated_at"])
    return prev, moved


def set_member_area_location(member, area):
    if area.latitude is None or area.longitude is None:
        raise ValueError(f"{area.name} has no map position yet, so it can't be used. Ask an admin to set it, or use GPS.")
    return set_member_location(member, area.latitude, area.longitude, source="area")


def set_rider_location(rider, lat, lng):
    lat, lng = geo.valid_point(lat, lng)
    prev = _pt(rider.latitude, rider.longitude, "gps", rider.location_updated_at)
    moved = _moved(prev, lat, lng)
    rider.latitude = geo.round_coord(lat, RIDER_PLACES)
    rider.longitude = geo.round_coord(lng, RIDER_PLACES)
    rider.location_updated_at = timezone.now()
    rider.save(update_fields=["latitude", "longitude", "location_updated_at"])
    return prev, moved


def set_merchant_location(merchant, lat, lng):
    lat, lng = geo.valid_point(lat, lng)
    merchant.latitude = geo.round_coord(lat, MERCHANT_PLACES)
    merchant.longitude = geo.round_coord(lng, MERCHANT_PLACES)
    merchant.location_source = "gps"
    merchant.location_updated_at = timezone.now()
    merchant.save(update_fields=["latitude", "longitude", "location_source", "location_updated_at"])


def clear_location(profile):
    """Stop sharing: wipe the stored coordinates."""
    profile.latitude = profile.longitude = None
    fields = ["latitude", "longitude"]
    if hasattr(profile, "location_updated_at"):
        profile.location_updated_at = None
        fields.append("location_updated_at")
    if hasattr(profile, "location_source"):
        profile.location_source = ""
        fields.append("location_source")
    profile.save(update_fields=fields)


def implausible_jump(prev, new_lat, new_lng, now=None, max_kmh=400.0, min_km=15.0) -> bool:
    """True if the new point implies travelling faster than any road vehicle since the previous update: a sign of
    spoofed GPS or a VPN. Only judged on recent previous points and real distances, so ordinary drift never trips it."""
    if prev is None or prev.updated_at is None:
        return False
    now = now or timezone.now()
    seconds = (now - prev.updated_at).total_seconds()
    if seconds > 3600:
        return False
    km = geo.haversine_km(prev.lat, prev.lng, new_lat, new_lng)
    return km >= min_km and geo.speed_kmh(km, seconds) > max_kmh


# ------------------------------------------------------------------------------------------------- offers
def _annotated(qs):
    return qs.annotate(
        _glat=Coalesce("merchant__latitude", "merchant__area__latitude", "area__latitude"),
        _glng=Coalesce("merchant__longitude", "merchant__area__longitude", "area__longitude"),
    )


def reach_km(radius_km: float, offer) -> float:
    """How far this offer can be seen from: the member's radius, shrunk by the merchant's own offer radius if set."""
    own = getattr(offer, "offer_radius_km", None)
    return min(radius_km, float(own)) if own else radius_km


def offers_near(qs, point, radius_km, cap=600):
    """[(offer, km)] nearest first. The database narrows to a bounding box; Python does the exact distance.
    Offers with no usable location (shop and area both unmapped) are excluded: we can't show they're near."""
    min_lat, max_lat, min_lng, max_lng = geo.bounding_box(point.lat, point.lng, radius_km)
    rows = _annotated(qs).filter(_glat__gte=min_lat, _glat__lte=max_lat, _glng__gte=min_lng, _glng__lte=max_lng)[:cap]
    out = []
    for o in rows:
        km = geo.haversine_km(point.lat, point.lng, float(o._glat), float(o._glng))
        if km <= reach_km(radius_km, o):
            out.append((o, km))
    out.sort(key=lambda t: t[1])
    return out


def check_member_can_claim(member, offer, gs=None):
    """(ok, message). Same rule as visibility: if you can see it, you can claim it."""
    gs = gs or geo_settings()
    if not gs.enforce:
        return True, ""
    p = member_point(member)
    if p is None:
        return False, "Share your location to claim offers near you."
    if p.source != "area" and (p.updated_at is None or p.updated_at < timezone.now() - timedelta(minutes=gs.claim_max_age_min)):
        return False, "Your location is out of date. Tap “Update location” and try again."
    target = offer_point(offer)
    if target is None:
        return False, "This seller's location isn't set yet, so we can't confirm it's near you."
    km = p.km_to(target)
    limit = reach_km(member_radius_km(member, gs), offer)
    if km > limit:
        return False, (f"This offer is {geo.format_distance(km)} away. You can claim offers within {limit:g} km of you; "
                       "move closer or increase your search distance.")
    return True, ""


# ------------------------------------------------------------------------------------------------- riders
def riders_near(point, radius_km, gs=None) -> int:
    from riders.models import Rider

    gs = gs or geo_settings()
    min_lat, max_lat, min_lng, max_lng = geo.bounding_box(point.lat, point.lng, radius_km)
    rows = Rider.objects.filter(
        status=Rider.Status.VERIFIED, is_available=True,
        location_updated_at__gte=timezone.now() - timedelta(minutes=gs.rider_max_age_min),
        latitude__gte=min_lat, latitude__lte=max_lat, longitude__gte=min_lng, longitude__lte=max_lng,
    ).values_list("latitude", "longitude")
    return sum(1 for la, lo in rows if geo.haversine_km(point.lat, point.lng, float(la), float(lo)) <= radius_km)


def job_pickup_point(job):
    return merchant_point(job.pickup_merchant)


def job_distance_km(rider_pt, job):
    target = job_pickup_point(job)
    return None if (rider_pt is None or target is None) else rider_pt.km_to(target)


def check_rider_can_accept(rider, job, gs=None):
    gs = gs or geo_settings()
    if not gs.enforce:
        return True, ""
    p = rider_point(rider, gs)
    if p is None:
        return False, "Turn on location sharing (and keep this page open) to accept jobs near you."
    km = job_distance_km(p, job)
    if km is None:
        return False, "This job's pickup location isn't set, so we can't confirm you're close enough."
    if km > gs.rider_job_radius_km:
        return False, f"This pickup is {geo.format_distance(km)} from you. You can accept jobs within {gs.rider_job_radius_km:g} km."
    return True, ""


# --------------------------------------------------------------------------------------------- UI helpers
def ago(dt) -> str:
    if dt is None:
        return ""
    secs = max(int((timezone.now() - dt).total_seconds()), 0)
    if secs < 90:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 86400:
        return f"{secs // 3600} h ago"
    return f"{secs // 86400} d ago"


def nearest_area_name(point, within_km=3.0):
    from .models import Area

    best, best_km = "", within_km
    for a in Area.objects.filter(is_active=True, latitude__isnull=False, longitude__isnull=False):
        km = geo.haversine_km(point.lat, point.lng, float(a.latitude), float(a.longitude))
        if km <= best_km:
            best, best_km = a.name, km
    return best


def member_location_state(member, gs=None) -> dict:
    gs = gs or geo_settings()
    p = member_point(member)
    base = {"enforce": gs.enforce, "radius_km": member_radius_km(member, gs), "radius_choices": gs.radius_choices,
            "default_radius_km": gs.default_radius_km}
    if p is None:
        return {**base, "state": "missing", "locked": gs.enforce}
    return {**base, "state": "ok", "locked": False, "source": p.source, "approx": p.approx,
            "updated": ago(p.updated_at), "area_label": nearest_area_name(p) if p.source == "area" else "",
            "age_s": "" if p.updated_at is None else int((timezone.now() - p.updated_at).total_seconds())}


def merchant_location_state(merchant) -> dict:
    if merchant.latitude is not None and merchant.longitude is not None:
        return {"state": "gps", "label": "Set from your device", "updated": ago(merchant.location_updated_at), "ok": True}
    if _area_point(merchant.area) is not None:
        return {"state": "approx", "label": f"Using the centre of {merchant.area.name} (approximate)", "updated": "", "ok": True}
    return {"state": "missing", "label": "Not set", "updated": "", "ok": False}
