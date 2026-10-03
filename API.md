# API Reference

Interactive docs (generated from the real code, always current):
`/api/docs/` (Swagger UI), `/api/redoc/` (Redoc), `/api/schema/` (raw
OpenAPI YAML). This file is a human-oriented map of what's there and how
auth works — for exact request/response shapes, use the interactive
docs or read the serializer in question.

## Auth model

Session-based. Log in via the server-rendered `/accounts/login/` (or
POST credentials there), then call API endpoints from the same
browser/client session — DRF's SessionAuthentication picks up the
session cookie. There is no separate token/JWT auth layer built yet.

Every response follows one shape:

```json
{"success": true, "data": {...}}
{"success": false, "error": {"code": "SOME_CODE", "message": "...", "details": {}}}
```

## Versioning

Everything lives under `/api/v1/`.

## Endpoint map, by who calls it

### Member

| Endpoint | Method | Notes |
|---|---|---|
| `/api/v1/member/subscription/` | GET | Current subscription, or null |
| `/api/v1/member/subscription/renew/` | POST | Opens a pending payment (bare — see `payments/initiate/` for the real ioTec-backed flow) |
| `/api/v1/member/subscription/pause/` | POST | |
| `/api/v1/member/offers/<id>/claim/` | POST | Reserves stock, generates a claim code |
| `/api/v1/member/claims/` | GET | |
| `/api/v1/member/claims/cancel/` | POST | body: {code} |
| `/api/v1/member/savings/` | GET | Confirmed/possible/monthly totals, computed live |
| `/api/v1/member/savings/history/` | GET | Last 6 months |
| `/api/v1/member/delivery/request/` | POST | body: {claim_code, dropoff_area, dropoff_address, delivery_type, fare} |
| `/api/v1/member/complaints/` | GET/POST | |
| `/api/v1/member/requests/` | GET/POST | Item requests — ask for something not currently offered |
| `/api/v1/member/requests/<id>/fulfill/` | POST | body: {response_id} (optional) |
| `/api/v1/member/requests/<id>/cancel/` | POST | |
| `/api/v1/member/offers/nearby/` | GET | query: area_id, category_id, q, sort (cheapest/biggest_saving/newest). Area-based, not lat/lng radius — see note below |
| `/api/v1/offers/categories/` | GET | Any authenticated role |
| `/api/v1/payments/initiate/` | POST | body: {purpose: "subscription", method, phone or email} — the real ioTec-backed payment flow |
| `/api/v1/payments/<id>/` | GET | Owner-scoped |

### Merchant

| Endpoint | Method | Notes |
|---|---|---|
| `/api/v1/merchant/claims/` | GET | Only this merchant's claims |
| `/api/v1/merchant/claims/redeem/` | POST | body: {code} — code, never an ID, to prevent enumeration |
| `/api/v1/merchant/offers/` | GET/POST | Own offers; create always starts PENDING (needs agent/admin approval) |
| `/api/v1/merchant/offers/<id>/` | PATCH/DELETE | Editing an active offer resets it to PENDING for re-approval; delete blocked if the offer has claims |
| `/api/v1/merchant/offers/<id>/pause/` | POST | |
| `/api/v1/merchant/requests/` | GET | Open item requests in the merchant's area |
| `/api/v1/merchant/requests/<id>/respond/` | POST | body: {message, price} — one response per merchant per request |
| `/api/v1/promotions/packages/` | GET | Available promotion packages |
| `/api/v1/merchant/promotions/` | GET | This merchant's promotion purchase history |
| `/api/v1/merchant/promotions/purchase/` | POST | body: {offer_id, package_id, method, phone\|email} — ioTec-backed, boosts Offer.visibility_score once payment succeeds |

### Rider

| Endpoint | Method | Notes |
|---|---|---|
| `/api/v1/rider/jobs/` | GET | Open + own active jobs |
| `/api/v1/rider/jobs/<id>/accept/` | POST | |
| `/api/v1/rider/jobs/<id>/arrived/` | POST | |
| `/api/v1/rider/jobs/<id>/picked-up/` | POST | Issues the delivery OTP |
| `/api/v1/rider/jobs/<id>/on-route/` | POST | |
| `/api/v1/rider/jobs/<id>/delivered/` | POST | body: {otp} |
| `/api/v1/rider/jobs/<id>/failed/` | POST | body: {reason} |
| `/api/v1/rider/earnings/` | GET | |
| `/api/v1/rider/balance/` | GET | Available-to-withdraw |
| `/api/v1/rider/withdraw/` | POST | body: {amount, phone} |
| `/api/v1/rider/withdrawals/` | GET | |
| `/api/v1/rider/routes/` | GET/POST | Create a shared-route trip (origin/destination area + departure time) |
| `/api/v1/rider/routes/<id>/publish/` | POST | Draft -> published, opens it for job attachment |
| `/api/v1/rider/routes/<id>/attach/<job_id>/` | POST | Combines accept + group-into-route in one step |
| `/api/v1/rider/routes/<id>/complete/` | POST | Only once every attached package is terminal |
| `/api/v1/rider/routes/<id>/cancel/` | POST | |

### Agent

| Endpoint | Method | Notes |
|---|---|---|
| `/api/v1/agent/dashboard/` | GET | |
| `/api/v1/agent/merchants-to-verify/` | GET | Scoped to the agent's assigned areas |
| `/api/v1/agent/merchants/<id>/verify/` | POST | body: {outcome, checklist, notes} |
| `/api/v1/agent/riders-to-verify/` | GET | |
| `/api/v1/agent/riders/<id>/verify/` | POST | |
| `/api/v1/agent/prices/` | GET/POST | Field-collected prices |
| `/api/v1/agent/earnings/` | GET | |
| `/api/v1/agent/complaints/` | GET | Open/investigating in the agent's areas |
| `/api/v1/agent/complaints/<id>/start/` | POST | |
| `/api/v1/agent/complaints/<id>/resolve/` | POST | body: {resolution_note} |
| `/api/v1/agent/complaints/<id>/escalate/` | POST | body: {note} |
| `/api/v1/agent/offers-to-approve/` | GET | Pending offers in the agent's areas |
| `/api/v1/agent/offers/<id>/approve/` | POST | Moves PENDING -> ACTIVE |
| `/api/v1/agent/offers/<id>/reject/` | POST | body: {reason} — moves PENDING -> REJECTED |

### Admin (capability-gated — see SECURITY.md)

| Endpoint | Method | Capability required |
|---|---|---|
| `/api/v1/admin/agents/` | GET/POST | agent_manage |
| `/api/v1/admin/users/<uuid>/suspend/` | POST | users_suspend |
| `/api/v1/admin/users/<uuid>/reactivate/` | POST | users_suspend |
| `/api/v1/admin/reports/summary/` | GET | reports_view |

### Any authenticated role

| Endpoint | Method | Notes |
|---|---|---|
| `/api/v1/notifications/` | GET | Own notifications |
| `/api/v1/notifications/<id>/read/` | POST | |
| `/api/v1/notifications/preferences/` | GET/PATCH | |
| `/api/v1/member/referrals/` | GET | Member only — own referral code, referred count, pending/credited reward totals |

### Provider callbacks (not for frontend use)

| Endpoint | Method | Auth |
|---|---|---|
| `/api/v1/payments/callback/iotec/collection/` | POST | X-Callback-Secret header |
| `/api/v1/payments/callback/iotec/disbursement/` | POST | X-Callback-Secret header |

### Server-rendered (not JSON API — /accounts/, not /api/v1/)

Registration, login, logout, phone verification (+ resend), password
reset (request + confirm), role switching. See `accounts/urls.py`.

## What's NOT built yet

Referral rewards are tracked and visible but not yet spendable/
redeemable against a real payment (see members app notes). SMS is sent
through the ioTec Messaging API (see notifications/services/sms_gateway.py
and the "SMS (ioTec Messaging)" section of DEPLOYMENT.md).

Note on SharedRoute: a route is a grouping/visibility construct on top
of the existing per-job delivery state machine — attaching a job to a
route doesn't change its own tracking or commission math at all, it
just groups several `delivery_type=shared_route` jobs under one
rider trip with a capacity limit.

Note on `/api/v1/member/offers/nearby/`: "nearby" is area-based (matches
this codebase's data model — `Offer.area` is a FK to `core.Area`, not a
lat/lng point), per the spec's own documented fallback for when PostGIS
isn't available. True radius-based search would need Offer to carry
coordinates and a PostGIS-backed query.
