"""Address search ("drop-off geocoding") and reverse lookup.

Runs on the server on purpose:
* the browser's CSP stays ``connect-src 'self'`` (no third-party calls from the page),
* answers are cached, so typing the same landmark twice costs nothing,
* one shared, rate-limited identity talks to the geocoder (Nominatim's policy: identify yourself, ~1 request/second).

It always degrades gracefully: with the geocoder switched off or unreachable, search still returns matching areas and
shops from our own database, and reverse lookup falls back to "Near <nearest area>". Users can always drop a pin by hand.
"""
from __future__ import annotations

import hashlib
import logging

import requests
from django.conf import settings
from django.core.cache import cache

from merchants.models import Merchant

from ..utils import active_areas_with_centres, in_uganda, nearest_area, valid_coords

logger = logging.getLogger("geo")

# Nominatim viewbox (left, top, right, bottom) around greater Kampala: results inside it rank higher (not a hard limit).
KAMPALA_VIEWBOX = "32.35,0.55,32.85,0.05"
SEARCH_TTL = 7 * 24 * 3600
REVERSE_TTL = 24 * 3600


def _clean(q: str) -> str:
    return " ".join(str(q or "").split())[:120]


def _headers():
    ua = settings.GEOCODER_USER_AGENT
    if settings.GEOCODER_EMAIL:
        ua = f"{ua} ({settings.GEOCODER_EMAIL})"
    return {"User-Agent": ua, "Accept-Language": "en"}


def _params(extra: dict) -> dict:
    params = {"format": "jsonv2", **extra}
    if settings.GEOCODER_EMAIL:
        params["email"] = settings.GEOCODER_EMAIL
    return params


def _short_label(display_name: str) -> str:
    parts = [p.strip() for p in str(display_name or "").split(",") if p.strip()]
    # "Kireka Market, Kireka, Kira Municipality, Wakiso, Central Region, 00000, Uganda" -> first four parts
    return ", ".join(parts[:4])[:200]


def local_matches(query: str, limit: int = 5) -> list[dict]:
    """Areas and verified shops from our own database whose name/address contains the query."""
    out = []
    for area in active_areas_with_centres():
        if query.lower() in area.name.lower():
            out.append({"label": f"{area.name} (area centre)", "lat": float(area.latitude), "lng": float(area.longitude),
                        "area": area.name, "kind": "area"})
    shops = Merchant.objects.filter(
        status=Merchant.Status.VERIFIED, latitude__isnull=False, longitude__isnull=False
    ).select_related("area")
    from django.db.models import Q

    for m in shops.filter(Q(business_name__icontains=query) | Q(address__icontains=query))[:limit]:
        out.append({"label": f"{m.business_name}" + (f", {m.address}" if m.address else ""), "lat": float(m.latitude),
                    "lng": float(m.longitude), "area": m.area.name, "kind": "shop"})
    return out[:limit]


def _remote_search(query: str, limit: int):
    """List of results, or None when the geocoder is unavailable (so the caller can tell 'no match' from 'down')."""
    base = settings.GEOCODER_BASE_URL.rstrip("/")
    if not base:
        return None
    key = "geo:fwd:" + hashlib.sha1(query.lower().encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached
    # Shared politeness: at most ~1 outgoing request per second across all workers.
    if not cache.add("geo:geocoder-slot", 1, timeout=1):
        return None
    try:
        resp = requests.get(
            f"{base}/search",
            params=_params({"q": query, "countrycodes": "ug", "viewbox": KAMPALA_VIEWBOX, "bounded": 0, "limit": limit}),
            headers=_headers(), timeout=settings.GEOCODER_TIMEOUT,
        )
        resp.raise_for_status()
        rows = resp.json()
    except (requests.RequestException, ValueError):
        logger.warning("Geocoder search failed", exc_info=True)
        return None
    results = []
    for row in rows if isinstance(rows, list) else []:
        pt = valid_coords(row.get("lat"), row.get("lon"))
        if pt and in_uganda(*pt):
            results.append({"label": _short_label(row.get("display_name")), "lat": pt[0], "lng": pt[1], "kind": "address"})
    cache.set(key, results, SEARCH_TTL if results else 24 * 3600)
    return results


def search(query: str, limit: int = 5) -> dict:
    """{"results": [{label, lat, lng, area, kind}], "available": bool}. ``available`` is False when the external
    geocoder could not be reached (local matches are still returned)."""
    q = _clean(query)
    if len(q) < 3:
        return {"results": [], "available": True}
    results = local_matches(q, limit)
    remote = _remote_search(q, limit)
    available = remote is not None or not settings.GEOCODER_BASE_URL
    seen = {(round(r["lat"], 4), round(r["lng"], 4)) for r in results}
    areas = active_areas_with_centres()
    for r in remote or []:
        k = (round(r["lat"], 4), round(r["lng"], 4))
        if k in seen:
            continue
        seen.add(k)
        near = nearest_area(r["lat"], r["lng"], max_km=25, areas=areas)
        r["area"] = near[0].name if near else None
        results.append(r)
    return {"results": results[:limit], "available": available}


def reverse(lat, lng) -> dict:
    """Best human label for a point. Never raises: falls back to 'Near <area>' then 'Pinned location'."""
    pt = valid_coords(lat, lng)
    if pt is None or not in_uganda(*pt):
        return {"label": "", "lat": None, "lng": None, "area": None, "approximate": True, "valid": False}
    areas = active_areas_with_centres()
    near = nearest_area(pt[0], pt[1], max_km=25, areas=areas)
    area_name = near[0].name if near else None
    label = ""
    base = settings.GEOCODER_BASE_URL.rstrip("/")
    if base:
        key = f"geo:rev:{round(pt[0], 4)}:{round(pt[1], 4)}"
        label = cache.get(key) or ""
        if not label and cache.add("geo:geocoder-slot", 1, timeout=1):
            try:
                resp = requests.get(
                    f"{base}/reverse", params=_params({"lat": pt[0], "lon": pt[1], "zoom": 18}),
                    headers=_headers(), timeout=settings.GEOCODER_TIMEOUT,
                )
                resp.raise_for_status()
                label = _short_label(resp.json().get("display_name"))
                if label:
                    cache.set(key, label, REVERSE_TTL)
            except (requests.RequestException, ValueError, AttributeError):
                logger.warning("Geocoder reverse lookup failed", exc_info=True)
    approximate = not label
    if not label:
        label = f"Near {area_name}" if area_name else "Pinned location"
    return {"label": label, "lat": pt[0], "lng": pt[1], "area": area_name, "approximate": approximate, "valid": True}
