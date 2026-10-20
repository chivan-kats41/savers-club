"""Pure geographic helpers (no database): validation, distance, bounding boxes, formatting.

Distances use the haversine formula on a sphere (error < 0.5%), which is far more accurate than the "vicinity" needs.
"""
import math

EARTH_RADIUS_KM = 6371.0088


def valid_point(lat, lng):
    """Return (lat, lng) as floats or raise ValueError. Rejects NaN/inf, out-of-range values and (0, 0)."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        raise ValueError("Latitude and longitude must be numbers.")
    if not (math.isfinite(lat) and math.isfinite(lng)):
        raise ValueError("Latitude and longitude must be real numbers.")
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        raise ValueError("That location is outside the valid range.")
    if lat == 0.0 and lng == 0.0:
        raise ValueError("That location isn't valid (a GPS default, not a real place).")
    return lat, lng


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def bounding_box(lat, lng, radius_km):
    """(min_lat, max_lat, min_lng, max_lng) that CONTAINS the circle: a cheap pre-filter a database can use with plain
    range comparisons; the exact haversine check is then done on the few rows that survive."""
    dlat = math.degrees(radius_km / EARTH_RADIUS_KM)
    cos_lat = max(math.cos(math.radians(lat)), 1e-6)
    dlng = math.degrees(radius_km / (EARTH_RADIUS_KM * cos_lat))
    return max(-90.0, lat - dlat), min(90.0, lat + dlat), max(-180.0, lng - dlng), min(180.0, lng + dlng)


def round_coord(value, places):
    """Privacy by rounding: 3 places ~ 110 m, 4 ~ 11 m, 5 ~ 1 m."""
    return round(float(value), places)


def format_distance(km) -> str:
    if km is None:
        return ""
    if km < 0.95:
        return f"{max(int(round(km * 1000 / 10.0) * 10), 10)} m"
    return f"{km:.1f} km"


def speed_kmh(km, seconds) -> float:
    return float("inf") if seconds <= 0 else km / (seconds / 3600.0)
