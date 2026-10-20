# Geo-locking: only what's near you

Like Uber showing only nearby drivers: **members see (and can claim) only offers near them, riders see (and can accept) only
delivery jobs near them, and members see how many riders are close.** Everything is decided on the server.

## How it works for each person

**Member.** The page opens with a gate: *Share your location to see deals near you* (or "Use this area instead"). After that the page
shows only offers within the member's distance (default **5 km**; they can choose 1, 2, 5, 10 or 25), nearest first, each with its
real distance ("300 m away"). A bar at the top shows where they are, the distance, "N riders nearby", and buttons to update, switch to an
area, or **stop sharing**. A member can't claim what they can't see: a claim for a far offer is refused with the distance.

**Merchant.** Sets the shop location once, *while at the shop* (Merchant page > Shop location > "Use my current location"). Until then the
area centre is used and labelled approximate. With no position at all, the shop can't post offers (an invisible offer would be pointless).

**Rider.** Shares live location while their page is open (updates every 30 s). Open jobs are only listed if the pickup is within **5 km**,
nearest shown with distance, and accepting a far job is refused. No live location = no open jobs. They can stop sharing at any time.

**Super admin.** Admin's own member/merchant/rider/agent profiles follow the same rules (share a location or pick an area to see deals).

## Where locations come from
| Who | Source | Kept as |
|---|---|---|
| Member | browser GPS, or the centre of an area they pick | latest point only, ~110 m precision |
| Merchant | browser GPS at the shop, else area centre (approximate) | ~1 m precision |
| Rider | browser GPS, live while the page is open | latest point only, ~11 m precision |

Distances use the haversine formula; the database narrows candidates with a cheap bounding box first. An offer is visible when
`distance <= min(member distance, the offer's own reach if the merchant set one)`.

## Admin: what you can change (Admin console > Settings)
System settings (live, no deploy): `geo.enforce` (true/false, the master switch), `geo.default_radius_km` (5), `geo.max_radius_km` (25),
`geo.rider_job_radius_km` (5), `geo.rider_location_max_age_minutes` (10), `geo.claim_location_max_age_minutes` (60), `geo.max_accuracy_m` (5000).
Run `python manage.py seed_system_settings` once to add these rows (defaults apply even without them).

**Area map positions** (new card): every area has a latitude/longitude. The ones filled in for existing areas are **approximate
(about 1-2 km)**: check them on a map and correct them. An area without a position can't be used for "near me".

## Privacy and security
* Location is personal data. Only the **latest point** is stored (no history), rounded, and **never shown to anyone else**: members see
  a rider *count*, never rider positions; merchants never see customers' positions.
* A person can **stop sharing** any time (the stored point is wiped). Browsers ask permission; we only ask on a button press, or silently
  when permission was already granted.
* The API validates everything (real numbers, valid ranges, rejects 0,0 and GPS readings less accurate than 5 km), is CSRF-protected and
  rate limited. A rider whose position "jumps" faster than any vehicle is rejected; a member's is logged for review.
* `Permissions-Policy: geolocation=(self)`: only this site may use location.
* Browsers only allow geolocation on **https** (or localhost while developing). In production you must serve the site over https.

## Honest limits
* A phone/browser reports its own position, so a determined person with a GPS-spoofing app can fake it. Mitigations (accuracy cap, jump
  detection, rounding) reduce casual abuse but aren't proof. The real safeguard stays in person: a claim code is only redeemed by the merchant at the shop.
* Desktop browsers give coarse positions (Wi-Fi/IP). Phones are accurate.
* A web page can't track in the background: riders must keep their page open to stay "live".
* Not included yet: map view, ETA/route, drop-off geocoding, push notifications, location history.

## Upgrading an existing install
`python manage.py migrate` (adds the location columns and fills approximate area positions, never overwriting yours), then
`python manage.py seed_system_settings`. Verified on a copy of the original database: all 13 areas positioned, all 8 merchants placed at
their area centre, all 6 offers stay visible.

## Tests
`python manage.py test` (Python, incl. 50 geo tests) and `NODE_PATH=... node hub/static_tests/geo.test.js` (browser behaviour of geo.js).
