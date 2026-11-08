# Location, maps, ETA and push notifications

## What members, riders and merchants get
| Feature | Where | How it works |
|---|---|---|
| **Hot deals near you** | Landing page `/`, member page | Signed-in members see deals ranked around *where they are*: live/saved location, else the area they picked by hand ("I'm in Kireka"), else their home area. Visitors can tap **Near me**. Ranking = closeness + discount depth + deals ending soon + low stock + seller boost. |
| **Geo-lock** | Landing, alerts, `/api/v1/geo/nearby-deals/` | A merchant's own radius (`Offer.offer_radius_km`) is honoured: farther away than that, the deal isn't shown. The member search page keeps such offers but flags them "Far from you". |
| **Map view** | Landing, member page | List/Map toggle (Leaflet, self-hosted). Your position is a blue dot; shops without a pin appear at their area centre and are labelled approximate. |
| **Drop-off geocoding** | Member > Delivery | Type a landmark (server-side search, cached), tap **Use my location**, or drop/drag a pin. Pin is validated: inside Uganda and within `geo.dropoff_max_km_from_area` of the chosen area. Works without any of it, exactly as before. |
| **Route + ETA** | Customer **Track** button, rider **Map** button | OSRM road route when reachable, otherwise a labelled straight-line estimate. Customer ETA = rider to shop + 5 min handover + shop to home. |
| **Live rider position** | Rider > Live location | Opt-in toggle. Recorded only while the rider has an accepted delivery; the customer sees it only for their own job, only while it's active. Customer is told once when the rider is within ~1 km. |
| **Location history** | Member > Where you are | Opt-in twice (remember location, then keep history). Review, delete one/all, download. Auto-deleted after `geo.history_retention_days` (30). |
| **Push notifications** | Member and rider pages | Web Push (VAPID). Every notification also goes to subscribed devices. Opt-in **hot deal near me** alerts: max 1/day, not 21:00-07:00, never SMS, never the same offer twice. |
| **Shop pin** | Merchant dashboard | Merchants pin their exact shop (search, "I'm at my shop", or drag). Audited. Improves their rank for nearby members. |

## Privacy design (Uganda Data Protection and Privacy Act 2019: have counsel review the wording)
- Location sharing and history are **off by default** and separate opt-ins. Turning sharing off deletes the last position.
- "Near me" on the landing page sends coordinates only as a transient query. **Nothing is stored** unless the signed-in user opted in.
- Member history is rounded to ~11 m; only the owner can read it; no admin screen shows it.
- Rider positions keep full precision (the customer needs them) and are deleted after `geo.rider_live_retention_days` (7).
- Run `python manage.py purge_location_history` (also in `run_periodic` and the Celery beat schedule).

## Setup
1. `pip install -r requirements.txt` (adds `pywebpush`), then `python manage.py migrate` (fills approximate area centres; see below).
2. Push: `python manage.py generate_vapid_keys` and put the three `VAPID_*` values in `.env`. Until then the push card stays hidden and nothing is sent.
3. Set `GEOCODER_EMAIL` to a real contact address (Nominatim's policy).
4. Run `python manage.py seed_system_settings` to expose the `geo.*` tunables in Admin > Settings.
5. Schedule: `run_periodic` already covers `purge_location_history` and `send_nearby_deal_alerts`; with Celery beat they're in `config/celery.py`.

## Things you must check or decide
- **Area centres are approximate** (`core/migrations/0005_area_coordinates.py`, entered from general knowledge, ~1 km). Verify each on a map and correct in Admin > Areas. A wrong centre shifts every "near you" distance for sellers who have not pinned their shop.
- **Tiles/geocoder/router default to free public services** (OpenStreetMap, Nominatim, OSRM demo). They are not meant for production traffic. Change `MAP_TILE_URL`, `GEOCODER_BASE_URL`, `OSRM_BASE_URL` to hosted or self-run ones when you grow; no code change needed (the CSP follows `MAP_TILE_URL`).
- **iPhone push** works only after the person adds the site to their Home Screen (Apple's rule). Needs HTTPS in production.
- **Rider tracking is browser-based**: it works while the rider page is open and the phone screen is on. For reliable background tracking you need a native app.
- **IP-based location is not used** (it can't tell Kireka from Mutungo). The browser's GPS or the manual area picker is.
- The SQL files for the three new tables were written by hand: validate on MySQL (see `database/README.md`).

## Troubleshooting: map shows "403 Access blocked" tiles
OpenStreetMap refuses tile requests that carry no `Referer` header. The site sends none to other origins
(`SECURE_REFERRER_POLICY = "same-origin"`), so the tile images alone send the bare origin (`MAP_TILE_REFERRER_POLICY=origin`).
If you still see it: hard-refresh (the browser cached the blocked tiles), make sure you are not on a file:// page, and note that
OSM may also refuse very heavy traffic: switch `MAP_TILE_URL` to a hosted provider.

## Security notes
- Push `endpoint` is user-supplied and the server POSTs to it, so it is restricted to https and the real push-service hosts (SSRF guard, `PUSH_ALLOWED_HOST_SUFFIXES`).
- CSP gains exactly one entry: the tile host in `img-src`. `connect-src` stays `'self'`: geocoding and routing are proxied by the server.
- All server text is inserted into the page with `textContent` (tests include an `<img onerror>` deal name).
- Geocode/route endpoints require login and are rate limited (`geocode`, `route`, `rider_ping`, `push` scopes).

## API (all under `/api/v1/`, JSON `{success, data|error}`)
`GET geo/nearby-deals/?lat&lng&limit&radius` (public) · `GET geo/geocode/?q` · `GET geo/reverse/?lat&lng` · `GET geo/route/?from_lat&from_lng&to_lat&to_lng` ·
`GET|PATCH geo/me/` · `POST geo/me/ping/` · `GET|DELETE geo/me/history/` · `DELETE geo/me/history/<id>/` · `GET geo/me/history/export/` ·
`POST merchant/location/` · `GET member/delivery/<id>/track/` · `POST rider/location/` · `GET rider/jobs/<id>/nav/` ·
`GET push/` · `POST push/subscribe/` · `POST push/unsubscribe/` · `POST push/test/` · `PATCH notifications/preferences/` (adds `push_enabled`, `deal_alerts_enabled`).
Delivery request accepts optional `dropoff_lat`, `dropoff_lng`, `dropoff_geocoded`.
