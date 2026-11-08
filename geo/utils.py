"""Small, dependency-free geography helpers shared by every geo feature.

Everything here is pure Python so it behaves identically on SQLite and MySQL (no GIS extension needed).
"""
from __future__ import annotations

import math
from decimal import Decimal

EARTH_RADIUS_KM = 6371.0088

# Rough bounding box of Uganda (south, west, north, east). Used as a sanity check on coordinates that arrive from a
# browser or a geocoder: it is not a border, just "is this plausibly a Ugandan location, not 0,0 or a typo".
UGANDA_BBOX = (-1.6, 29.5, 4.3, 35.1)


def to_float(value):
    """float(value) or None for anything that is not a finite number (None, '', 'abc', NaN, inf)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def valid_coords(lat, lng):
    """(lat, lng) as floats when both are finite and in range, else None."""
    la, lo = to_float(lat), to_float(lng)
    if la is None or lo is None or not (-90 <= la <= 90) or not (-180 <= lo <= 180):
        return None
    return la, lo


def in_uganda(lat: float, lng: float) -> bool:
    s, w, n, e = UGANDA_BBOX
    return s <= lat <= n and w <= lng <= e


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def dec6(value) -> Decimal:
    """Decimal with 6 places (≈ 0.1 m), the precision of every lat/lng column."""
    return Decimal(str(round(float(value), 6))).quantize(Decimal("0.000001"))


def distance_label(km: float | None) -> str:
    if km is None:
        return ""
    if km < 0.95:
        return f"{max(50, int(round(km * 1000 / 50.0) * 50))} m away"
    return f"{km:.1f} km away"


def area_point(area):
    """(lat, lng) of an Area centroid, or None when the admin has not set one."""
    if area is None or area.latitude is None or area.longitude is None:
        return None
    return float(area.latitude), float(area.longitude)


def merchant_point(merchant):
    """(lat, lng, precise) for a merchant: its own pin when set (precise), else its area's centroid (approximate)."""
    if merchant.latitude is not None and merchant.longitude is not None:
        return float(merchant.latitude), float(merchant.longitude), True
    pt = area_point(merchant.area)
    return (pt[0], pt[1], False) if pt else None


def active_areas_with_centres():
    from core.models import Area

    return list(Area.objects.filter(is_active=True, latitude__isnull=False, longitude__isnull=False))


def nearest_area(lat: float, lng: float, max_km: float | None = None, areas=None):
    """(Area, km) of the active area whose centroid is closest to the point, or None.
    Pass ``areas`` (from active_areas_with_centres) when looking up many points to avoid re-querying."""
    best = None
    for area in (areas if areas is not None else active_areas_with_centres()):
        km = haversine_km(lat, lng, float(area.latitude), float(area.longitude))
        if best is None or km < best[1]:
            best = (area, km)
    if best is None or (max_km is not None and best[1] > max_km):
        return None
    return best
