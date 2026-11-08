"""Route + ETA between two points.

Uses OSRM (road network) when ``OSRM_BASE_URL`` is set and reachable; otherwise, or on any failure, falls back to a
straight-line estimate (distance x detour factor / average boda speed) so the UI always has *an* ETA. Every result says
which one it is (``source``: "osrm" or "estimate") so the interface can label estimates honestly.
"""
from __future__ import annotations

import logging
import math
from datetime import timedelta
from decimal import Decimal

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from core.services import get_setting_decimal

from ..utils import haversine_km, valid_coords

logger = logging.getLogger("geo")

ROUTE_TTL = 600          # 10 minutes: the same trip is looked up repeatedly while a delivery is tracked
DETOUR_FACTOR = 1.35     # roads are longer than the straight line
MAX_GEOMETRY_POINTS = 250


def _speed_kmh() -> float:
    return float(get_setting_decimal("geo.boda_speed_kmh", Decimal("22")))


def estimate(a, b) -> dict:
    straight = haversine_km(a[0], a[1], b[0], b[1])
    km = straight * DETOUR_FACTOR
    minutes = max(1, math.ceil(km / max(_speed_kmh(), 5.0) * 60))
    return {"distance_km": round(km, 2), "duration_min": minutes, "geometry": [[a[0], a[1]], [b[0], b[1]]],
            "source": "estimate"}


def _osrm(a, b):
    base = settings.OSRM_BASE_URL.rstrip("/")
    if not base:
        return None
    url = f"{base}/route/v1/{settings.OSRM_PROFILE}/{a[1]},{a[0]};{b[1]},{b[0]}"
    try:
        resp = requests.get(url, params={"overview": "simplified", "geometries": "geojson"},
                            timeout=settings.ROUTING_TIMEOUT)
        resp.raise_for_status()
        route = resp.json()["routes"][0]
        coords = route["geometry"]["coordinates"]            # GeoJSON order is [lng, lat]
        step = max(1, len(coords) // MAX_GEOMETRY_POINTS)
        geometry = [[c[1], c[0]] for c in coords[::step]]
        if geometry[-1] != [coords[-1][1], coords[-1][0]]:
            geometry.append([coords[-1][1], coords[-1][0]])
        return {"distance_km": round(route["distance"] / 1000, 2),
                "duration_min": max(1, math.ceil(route["duration"] / 60)),
                "geometry": geometry, "source": "osrm"}
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        logger.warning("OSRM route lookup failed, using estimate", exc_info=True)
        return None


def route(origin, destination) -> dict:
    """origin/destination: (lat, lng). Returns {distance_km, duration_min, eta_at, geometry [[lat,lng],...], source}.
    Raises ValueError for invalid coordinates."""
    a = valid_coords(*origin)
    b = valid_coords(*destination)
    if a is None or b is None:
        raise ValueError("Invalid coordinates.")
    key = f"geo:route:{round(a[0], 4)},{round(a[1], 4)}:{round(b[0], 4)},{round(b[1], 4)}"
    result = cache.get(key)
    if result is None:
        result = _osrm(a, b) or estimate(a, b)
        cache.set(key, result, ROUTE_TTL if result["source"] == "osrm" else 60)
    result = dict(result)
    result["eta_at"] = (timezone.now() + timedelta(minutes=result["duration_min"])).isoformat()
    return result
