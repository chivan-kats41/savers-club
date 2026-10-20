"""APPROXIMATE area centre points (about +/- 1-2 km), so "within 5 km of me" works out of the box.

They are only a starting point for people who pick an area instead of using GPS, and for shops that haven't set an exact
location yet. Admins should check them on a map and correct them in Admin console > Settings > Area map positions.
Only areas whose position is still EMPTY are filled (matched by name); anything an admin set is never overwritten.
"""
from decimal import Decimal

CENTROIDS = {
    "Mutungo": ("0.329000", "32.649000"), "Kitintale": ("0.335000", "32.641000"), "Luzira": ("0.298000", "32.636000"),
    "Kireka": ("0.347000", "32.647000"), "Bweyogerere": ("0.354000", "32.670000"), "Makindye": ("0.283000", "32.595000"),
    "Nansana": ("0.365000", "32.529000"), "Nakawa": ("0.330000", "32.615000"), "Ntinda": ("0.352000", "32.612000"),
    "Katabi": ("0.083000", "32.477000"), "Entebbe": ("0.051000", "32.464000"), "Kampala": ("0.313600", "32.581100"),
    "Wakiso": ("0.404000", "32.459000"), "Mbarara": ("-0.607200", "30.654500"), "Mbuya II": ("0.318000", "32.615000"),
    "Kirombe": ("0.323000", "32.656000"), "Bugolobi": ("0.315000", "32.618000"),
}


def fill_empty_positions(Area) -> int:
    """Works with the real model or a migration's historical model. Returns how many areas were filled."""
    n = 0
    for name, (lat, lng) in CENTROIDS.items():
        n += Area.objects.filter(name=name, latitude__isnull=True, longitude__isnull=True).update(
            latitude=Decimal(lat), longitude=Decimal(lng))
    return n
