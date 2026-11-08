"""Which deals are *hot and near this person*?

Origin (where the person is), in order of trust:
  1. ``gps``          live coordinates sent with this request (never stored by this module)
  2. ``saved``        their last known fix, only if they opted in to sharing and it is recent
  3. ``manual_area``  an area they picked by hand ("I'm in Kireka right now")
  4. ``member_area``  the area chosen at registration

Ranking blends closeness, discount depth, urgency (expires soon), scarcity (few left) and the merchant's boost.
Geo-lock: a merchant's own ``offer_radius_km`` is respected: if the person is farther than that, the offer is not shown.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from core.models import Area
from core.services import get_setting_decimal
from members.models import Member

from ..models import UserLocation
from ..utils import area_point, distance_label, haversine_km, in_uganda, merchant_point, nearest_area, valid_coords
from .history import fresh_minutes

PRECISE_SOURCES = ("gps", "saved")


@dataclass
class Origin:
    lat: float | None
    lng: float | None
    area: Area | None
    source: str

    @property
    def precise(self) -> bool:
        return self.source in PRECISE_SOURCES

    @property
    def has_point(self) -> bool:
        return self.lat is not None and self.lng is not None

    @property
    def label(self) -> str:
        name = self.area.name if self.area else ""
        if self.source in PRECISE_SOURCES:
            return f"Near {name}" if name else "Your location"
        return name or "Your area"

    def as_dict(self) -> dict:
        return {"lat": self.lat, "lng": self.lng, "area": self.area.name if self.area else None,
                "source": self.source, "label": self.label, "precise": self.precise}


def _area_origin(area: Area, source: str) -> Origin:
    pt = area_point(area)
    return Origin(pt[0] if pt else None, pt[1] if pt else None, area, source)


def resolve_origin(user=None, lat=None, lng=None) -> Origin | None:
    pt = valid_coords(lat, lng)
    if pt and in_uganda(*pt):
        near = nearest_area(pt[0], pt[1], max_km=25)
        return Origin(pt[0], pt[1], near[0] if near else None, "gps")

    if user is not None and getattr(user, "is_authenticated", False):
        state = UserLocation.objects.select_related("area", "area_override").filter(user=user).first()
        if state is not None:
            if (state.share_location and state.latitude is not None and state.located_at
                    and state.located_at >= timezone.now() - timedelta(minutes=fresh_minutes())):
                return Origin(float(state.latitude), float(state.longitude), state.area, "saved")
            if state.area_override_id:
                return _area_origin(state.area_override, "manual_area")
        member = Member.objects.select_related("area").filter(user=user).first()
        if member is not None:
            return _area_origin(member.area, "member_area")
    return None


@dataclass
class Ranked:
    offer: object
    km: float | None
    precise: bool
    within: bool
    same_area: bool
    score: float
    lat: float | None
    lng: float | None
    locked: bool = False     # the merchant's own radius excludes this person

    @property
    def distance_text(self) -> str:
        if self.km is not None:
            txt = distance_label(self.km)
            return txt if self.precise else "≈ " + txt
        return "In your area" if self.same_area else ""


def _offer_point(offer):
    pt = merchant_point(offer.merchant)
    if pt:
        return pt
    ap = area_point(offer.area)
    return (ap[0], ap[1], False) if ap else None


def hot_score(offer, km, same_area, now) -> float:
    normal = float(offer.normal_price or 0)
    discount = min(1.0, max(0.0, float(offer.possible_saving) / normal)) if normal > 0 else 0.0
    proximity = math.exp(-km / 3.0) if km is not None else (0.6 if same_area else 0.1)
    hours_left = max(0.0, (offer.expires_at - now).total_seconds() / 3600)
    urgency = 1 - min(hours_left, 48.0) / 48.0
    scarcity = 1 - min(float(offer.quantity), 20.0) / 20.0
    boost = min(float(offer.visibility_score or 0), 100.0) / 100.0
    return 0.35 * proximity + 0.30 * discount + 0.15 * urgency + 0.10 * scarcity + 0.10 * boost


def default_radius_km() -> float:
    return float(get_setting_decimal("geo.nearby_radius_km", Decimal(str(getattr(settings, "GEO_NEARBY_RADIUS_KM", 6)))))


def rank_offers(offers, origin: Origin | None, radius_km: float | None = None, limit: int = 6,
                include_further: bool = True, apply_lock: bool = True) -> list[Ranked]:
    """Rank candidate offers for ``origin``.

    ``apply_lock=True`` (discovery surfaces) drops offers whose merchant radius excludes the person; with False they are
    kept but flagged ``locked`` (the member search page shows them with a "far from you" note instead of hiding them)."""
    now = timezone.now()
    radius = radius_km if radius_km else default_radius_km()
    ranked: list[Ranked] = []
    for o in offers:
        pt = _offer_point(o)
        km, precise = None, False
        if origin is not None and origin.has_point and pt is not None:
            km = haversine_km(origin.lat, origin.lng, pt[0], pt[1])
            precise = origin.precise and pt[2]
        same_area = bool(origin is not None and origin.area is not None and o.area_id == origin.area.pk)

        r = float(o.offer_radius_km) if o.offer_radius_km else 0.0
        locked = bool(r > 0 and km is not None and km > r + (0.0 if precise else 1.0))
        if locked and apply_lock:
            continue                                   # the merchant only serves this far out

        within = (km is not None and km <= radius) or (km is None and same_area)
        ranked.append(Ranked(o, km, precise, within, same_area, hot_score(o, km, same_area, now),
                             pt[0] if pt else None, pt[1] if pt else None, locked))
    ranked.sort(key=lambda r: (not r.within, -r.score))
    if not include_further:
        ranked = [r for r in ranked if r.within]
    return ranked[:limit]
