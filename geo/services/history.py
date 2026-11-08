"""Where-a-user-is bookkeeping: consent, last known position, history trail, retention.

Rules (also shown to the user in the UI):
* Nothing about a user's position is stored unless they turned ``share_location`` on. The trail is a second opt-in.
* Member history is rounded to 4 decimals (~11 m); the last-known fix to 5 (~1 m). Rider positions during a live delivery
  keep full precision, because the customer needs them, but are deleted after a short retention.
* Everything is user-deletable, and old rows are purged by ``purge_location_history``.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.services import get_setting_int

from ..models import LocationHistory, UserLocation
from ..utils import dec6, haversine_km, in_uganda, nearest_area, valid_coords

MIN_MOVE_KM = 0.10          # don't add a history row unless the user moved at least 100 m ...
MIN_INTERVAL_SECONDS = 600  # ... or 10 minutes have passed
RIDER_MIN_MOVE_KM = 0.025
RIDER_MIN_INTERVAL_SECONDS = 45


def history_retention_days() -> int:
    return max(1, get_setting_int("geo.history_retention_days", 30))


def rider_live_retention_days() -> int:
    return max(1, get_setting_int("geo.rider_live_retention_days", 7))


def fresh_minutes() -> int:
    return max(5, get_setting_int("geo.fresh_minutes", 120))


def get_state(user) -> UserLocation:
    state, _ = UserLocation.objects.select_related("area", "area_override").get_or_create(user=user)
    return state


def _r(value: float, places: int) -> float:
    return round(float(value), places)


@transaction.atomic
def update_settings(user, share_location=None, save_history=None, area_override="__keep__") -> UserLocation:
    """Change consent / manual area. Turning sharing off forgets the last known position immediately."""
    state = UserLocation.objects.select_for_update().get_or_create(user=user)[0]
    if share_location is not None:
        state.share_location = bool(share_location)
        if not state.share_location:
            state.latitude = state.longitude = state.accuracy_m = state.area = state.located_at = None
            state.save_history = False          # a trail without sharing makes no sense
    if save_history is not None and state.share_location:
        state.save_history = bool(save_history)
    if area_override != "__keep__":
        state.area_override = area_override      # an Area or None
    state.save()
    return state


def record_fix(user, lat, lng, accuracy=None, source=LocationHistory.Source.BROWSER, label="") -> dict:
    """Handle a position reported by the user's own device.

    Returns {"area": Area|None, "stored": bool, "history": bool}. A fix is only kept when the user opted in; either way
    the caller gets the nearest area back so the page can show "Near Kireka".
    """
    pt = valid_coords(lat, lng)
    if pt is None:
        raise ValidationError("Invalid coordinates.")
    if not in_uganda(*pt):
        raise ValidationError("That location is outside Uganda, where the service operates.")
    near = nearest_area(pt[0], pt[1], max_km=25)
    area = near[0] if near else None
    acc = None
    try:
        acc = max(0, min(int(float(accuracy)), 100000)) if accuracy not in (None, "") else None
    except (TypeError, ValueError):
        acc = None

    state = get_state(user)
    if not state.share_location:
        return {"area": area, "stored": False, "history": False}

    now = timezone.now()
    state.latitude, state.longitude = dec6(_r(pt[0], 5)), dec6(_r(pt[1], 5))
    state.accuracy_m, state.area, state.located_at = acc, area, now
    state.save(update_fields=["latitude", "longitude", "accuracy_m", "area", "located_at", "updated_at"])

    wrote = False
    if state.save_history:
        last = LocationHistory.objects.filter(user=user).exclude(
            source=LocationHistory.Source.RIDER_LIVE).order_by("-created_at").first()
        moved = last is None or haversine_km(float(last.latitude), float(last.longitude), pt[0], pt[1]) >= MIN_MOVE_KM
        aged = last is None or (now - last.created_at).total_seconds() >= MIN_INTERVAL_SECONDS
        if moved or aged:
            LocationHistory.objects.create(
                user=user, latitude=dec6(_r(pt[0], 4)), longitude=dec6(_r(pt[1], 4)), accuracy_m=acc, area=area,
                place_label=str(label or "")[:255], source=source,
            )
            wrote = True
    return {"area": area, "stored": True, "history": wrote}


def record_dropoff(user, lat, lng, label: str, job=None):
    """A drop-off the user chose for a delivery. Kept in their history only if they opted in to history."""
    pt = valid_coords(lat, lng)
    if pt is None:
        return None
    state = UserLocation.objects.filter(user=user).first()
    if not (state and state.save_history):
        return None
    near = nearest_area(pt[0], pt[1], max_km=25)
    return LocationHistory.objects.create(
        user=user, latitude=dec6(_r(pt[0], 4)), longitude=dec6(_r(pt[1], 4)), area=near[0] if near else None,
        place_label=str(label or "")[:255], source=LocationHistory.Source.DROPOFF, job=job,
    )


def record_rider_fix(rider_user, job, lat, lng, accuracy=None):
    """Rider position during an active delivery. Stored (with the job) so the customer can follow the trip.
    Returns the LocationHistory row (new or the existing latest one if the rider has barely moved)."""
    pt = valid_coords(lat, lng)
    if pt is None or not in_uganda(*pt):
        raise ValidationError("Invalid or out-of-country coordinates.")
    now = timezone.now()
    last = LocationHistory.objects.filter(
        user=rider_user, job=job, source=LocationHistory.Source.RIDER_LIVE).order_by("-created_at").first()
    if last is not None:
        gap = (now - last.created_at).total_seconds()
        moved = haversine_km(float(last.latitude), float(last.longitude), pt[0], pt[1])
        if gap < RIDER_MIN_INTERVAL_SECONDS and moved < RIDER_MIN_MOVE_KM:
            return last
    try:
        acc = max(0, min(int(float(accuracy)), 100000)) if accuracy not in (None, "") else None
    except (TypeError, ValueError):
        acc = None
    return LocationHistory.objects.create(
        user=rider_user, job=job, latitude=dec6(pt[0]), longitude=dec6(pt[1]), accuracy_m=acc,
        source=LocationHistory.Source.RIDER_LIVE,
    )


def latest_rider_fix(job):
    return LocationHistory.objects.filter(job=job, source=LocationHistory.Source.RIDER_LIVE).order_by("-created_at").first()


def clear_history(user) -> int:
    deleted, _ = LocationHistory.objects.filter(user=user).exclude(
        source=LocationHistory.Source.RIDER_LIVE).delete()
    return deleted


def purge_expired(now=None) -> dict:
    """Delete rows past their retention, and forget stale last-known fixes. Safe to run repeatedly."""
    now = now or timezone.now()
    cut_member = now - timedelta(days=history_retention_days())
    cut_rider = now - timedelta(days=rider_live_retention_days())
    n_member = LocationHistory.objects.exclude(source=LocationHistory.Source.RIDER_LIVE).filter(
        created_at__lt=cut_member).delete()[0]
    n_rider = LocationHistory.objects.filter(source=LocationHistory.Source.RIDER_LIVE, created_at__lt=cut_rider).delete()[0]
    n_state = UserLocation.objects.filter(located_at__lt=cut_member).update(
        latitude=None, longitude=None, accuracy_m=None, area=None, located_at=None)
    return {"history": n_member, "rider_live": n_rider, "stale_fixes": n_state}
