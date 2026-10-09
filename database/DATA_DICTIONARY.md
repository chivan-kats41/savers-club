# Data dictionary — 1K Saver Club database

Generated from the live MySQL schema and the model docstrings. **Do not edit by hand**: regenerate with the schema files (see `database/README.md`). Engine: InnoDB, charset `utf8mb4`, collation `utf8mb4_unicode_ci`.

**63 tables · 104 foreign-key columns · 131 secondary indexes**

Conventions: `id` is the primary key; UUID keys are stored as `char(32)`; money is `decimal(12,2)` in UGX; every datetime is stored in Africa/Kampala local time (see README, *Time zones*); `created_at`/`updated_at` are on most tables.

## Contents

- [Accounts & security](#accounts) (8 tables)
- [Platform core (areas, settings, audit)](#core) (4 tables)
- [Members & referrals](#members) (2 tables)
- [Subscriptions](#subscriptions) (4 tables)
- [Merchants](#merchants) (3 tables)
- [Offers, categories & interactions](#offers) (4 tables)
- [Claim codes & redemptions](#claims) (2 tables)
- [Savings records](#savings) (1 tables)
- [Item requests](#item_requests) (2 tables)
- [Deliveries, routes & pickup points](#deliveries) (6 tables)
- [Riders](#riders) (3 tables)
- [Agents, prices & tasks](#agents) (5 tables)
- [Complaints](#complaints) (3 tables)
- [Payments & withdrawals (ioTec)](#payments) (5 tables)
- [Promotions](#promotions) (2 tables)
- [Notifications](#notifications) (2 tables)
- [Django framework tables (auth, sessions, admin, migrations)](#framework) (7 tables)

<a id="accounts"></a>
## Accounts & security

### `accounts_emailverification`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `token` | char(32) | no | unique |
| `is_used` | tinyint(1) | no |  |
| `expires_at` | datetime(6) | no |  |
| `created_at` | datetime(6) | no |  |
| `user_id` | char(32) | no | FK → `accounts_user.id` |

### `accounts_loginattempt`

Every login attempt, success or failure, keyed by the identifier typed in (phone or email) — used for lockout/rate-limit decisions independent of whether that identifier resolves to a real user.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `identifier` | varchar(150) | no |  |
| `ip_address` | char(39) | yes |  |
| `success` | tinyint(1) | no |  |
| `created_at` | datetime(6) | no |  |
| `user_id` | char(32) | yes | FK → `accounts_user.id` |

Composite indexes: `(identifier,created_at)`

### `accounts_phoneverification`

Hashed OTP for phone verification / phone-based login / password reset. The raw code is never stored — only its SHA-256 hash.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `purpose` | varchar(20) | no |  |
| `code_hash` | varchar(64) | no |  |
| `attempts` | smallint unsigned | no |  |
| `max_attempts` | smallint unsigned | no |  |
| `is_used` | tinyint(1) | no |  |
| `expires_at` | datetime(6) | no |  |
| `created_at` | datetime(6) | no |  |
| `user_id` | char(32) | no | FK → `accounts_user.id` |

Composite indexes: `(user_id,purpose,is_used)`

### `accounts_securityevent`

Account-security-relevant events: password change, phone/email change, role switch, lockout triggered, etc. Distinct from core.AuditLog (which is the general-purpose, cross-domain audit trail) so security tooling can query just this table cheaply.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `event_type` | varchar(50) | no |  |
| `ip_address` | char(39) | yes |  |
| `user_agent` | varchar(255) | no |  |
| `metadata` | json | no |  |
| `created_at` | datetime(6) | no |  |
| `user_id` | char(32) | yes | FK → `accounts_user.id` |

Composite indexes: `(user_id,event_type,created_at)`

### `accounts_user`

Identity + primary role only for now. Multi-role assignment (a user who is both a Member and a Rider, with role-switching), phone/email verification records, login-attempt tracking, and granular permissions are added in Phase 2 — this model exists in Phase 1 purely so AUTH_USER_MODEL can be set before the first migration, as Django requires.

| Column | Type | Null | Notes |
|---|---|---|---|
| `password` | varchar(128) | no |  |
| `last_login` | datetime(6) | yes |  |
| `is_superuser` | tinyint(1) | no |  |
| `id` | char(32) | no | PK |
| `phone` | varchar(20) | no | unique |
| `email` | varchar(254) | yes | unique |
| `first_name` | varchar(150) | no |  |
| `last_name` | varchar(150) | no |  |
| `role` | varchar(20) | no |  |
| `phone_verified` | tinyint(1) | no |  |
| `email_verified` | tinyint(1) | no |  |
| `is_active` | tinyint(1) | no |  |
| `is_staff` | tinyint(1) | no |  |
| `date_joined` | datetime(6) | no |  |
| `totp_enabled` | tinyint(1) | no |  |
| `totp_secret` | varchar(64) | no |  |

### `accounts_user_groups`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `user_id` | char(32) | no | FK → `accounts_user.id` |
| `group_id` | int | no | FK → `auth_group.id` |

Composite indexes: `(user_id,group_id)` unique

### `accounts_user_user_permissions`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `user_id` | char(32) | no | FK → `accounts_user.id` |
| `permission_id` | int | no | FK → `auth_permission.id` |

Composite indexes: `(user_id,permission_id)` unique

### `accounts_userrole`

A role a user is permitted to switch into. `User.role` is the currently *active* role (drives dashboard/permission checks); UserRole is the set of roles they're allowed to switch between — e.g. someone can be both a Member and a Rider.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `role` | varchar(20) | no |  |
| `is_active` | tinyint(1) | no |  |
| `assigned_at` | datetime(6) | no |  |
| `user_id` | char(32) | no | FK → `accounts_user.id` |

Composite indexes: `(user_id,role)` unique

<a id="core"></a>
## Platform core (areas, settings, audit)

### `core_area`

A launch/service area (e.g. Mutungo, Kitintale). Backs geolocation and offer-radius logic across offers/deliveries/agents.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `name` | varchar(120) | no | unique |
| `is_launch_area` | tinyint(1) | no |  |
| `latitude` | decimal(9,6) | yes |  |
| `longitude` | decimal(9,6) | yes |  |
| `is_active` | tinyint(1) | no |  |

### `core_auditlog`

Immutable audit trail. Written to, never edited or deleted from application code — see core/admin.py for read-only enforcement.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `action` | varchar(100) | no |  |
| `object_type` | varchar(100) | no |  |
| `object_id` | varchar(64) | no |  |
| `ip_address` | char(39) | yes |  |
| `user_agent` | varchar(255) | no |  |
| `request_id` | varchar(64) | no |  |
| `metadata` | json | no |  |
| `actor_id` | char(32) | yes | FK → `accounts_user.id` |

Composite indexes: `(action,created_at)`; `(actor_id,created_at)`; `(object_type,object_id)`

### `core_riskevent`

A lightweight fraud/risk signal — repeated failed payments, OTP lockouts, suspicious redemption attempts, rapid account creation from one IP, etc. Per spec section 33: these inform admin review, they never auto-block a user off a single signal.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `event_type` | varchar(50) | no |  |
| `ip_address` | char(39) | yes |  |
| `metadata` | json | no |  |
| `reviewed` | tinyint(1) | no |  |
| `user_id` | char(32) | yes | FK → `accounts_user.id` |

Composite indexes: `(user_id,event_type,created_at)`

### `core_systemsetting`

Admin-configurable key/value business settings (subscription price, commission %, fees, limits, etc.) so nothing is hard-coded in views.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `key` | varchar(100) | no | unique |
| `value` | longtext | no |  |
| `description` | varchar(255) | no |  |
| `is_active` | tinyint(1) | no |  |

<a id="members"></a>
## Members & referrals

### `members_member`

Member profile. Subscription status lives on subscriptions.Subscription (Phase 4) — this model holds identity/area/referral only, so we don't duplicate a status that a real payment-backed model already owns.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `account_status` | varchar(20) | no |  |
| `referral_code` | varchar(16) | no | unique |
| `area_id` | bigint | no | FK → `core_area.id` |
| `referred_by_id` | bigint | yes | FK → `members_member.id` |
| `user_id` | char(32) | no | unique, FK → `accounts_user.id` |

### `members_referralreward`

One row per referred member who has activated a subscription for the first time — created automatically (see subscriptions.services. confirm_payment) the moment that first payment succeeds, so a referral is only ever rewarded once it's a real paying member, not just a signup. `referred_member` is OneToOne: each referred member can only generate one reward, ever.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `amount` | decimal(10,2) | no |  |
| `status` | varchar(20) | no |  |
| `credited_at` | datetime(6) | yes |  |
| `referred_member_id` | bigint | no | unique, FK → `members_member.id` |
| `referrer_id` | bigint | no | FK → `members_member.id` |

<a id="subscriptions"></a>
## Subscriptions

### `subscriptions_subscription`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `status` | varchar(20) | no |  |
| `current_period_start` | datetime(6) | yes |  |
| `current_period_end` | datetime(6) | yes |  |
| `auto_renew` | tinyint(1) | no |  |
| `member_id` | bigint | no | FK → `members_member.id` |
| `plan_id` | bigint | no | FK → `subscriptions_subscriptionplan.id` |

Composite indexes: `(member_id,status)`

### `subscriptions_subscriptionevent`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `event_type` | varchar(50) | no |  |
| `metadata` | json | no |  |
| `subscription_id` | bigint | no | FK → `subscriptions_subscription.id` |

### `subscriptions_subscriptionpayment`

Placeholder payment record for a subscription charge. The real ioTec integration (OAuth client, collection request, callback handling) is built in the payments app in Phase 7 — this model exists now so Subscription.renew() has somewhere authoritative to record 'a payment was requested' without faking success. Status only ever moves PENDING -> SUCCESS/FAILED via a real confirmation path; nothing in this app auto-activates a subscription from a frontend claim.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `external_reference` | char(32) | no | unique |
| `amount` | decimal(12,2) | no |  |
| `status` | varchar(20) | no |  |
| `provider` | varchar(30) | no |  |
| `provider_transaction_id` | varchar(100) | no |  |
| `subscription_id` | bigint | no | FK → `subscriptions_subscription.id` |

### `subscriptions_subscriptionplan`

Admin-configurable — nothing about price/period is hard-coded in application code. Default plan is UGX 1,000/month, but admins can add/edit plans (quarterly, yearly promo, etc.) without a deploy.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `code` | varchar(30) | no | unique |
| `label` | varchar(100) | no |  |
| `price` | decimal(12,2) | no |  |
| `period_days` | int unsigned | no |  |
| `is_active` | tinyint(1) | no |  |
| `is_popular` | tinyint(1) | no |  |
| `benefits` | json | no |  |

<a id="merchants"></a>
## Merchants

### `merchants_merchant`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `business_name` | varchar(150) | no |  |
| `vendor_type` | varchar(100) | no |  |
| `address` | varchar(255) | no |  |
| `latitude` | decimal(9,6) | yes |  |
| `longitude` | decimal(9,6) | yes |  |
| `phone` | varchar(20) | no |  |
| `whatsapp` | varchar(20) | no |  |
| `status` | varchar(20) | no |  |
| `verified_at` | datetime(6) | yes |  |
| `area_id` | bigint | no | FK → `core_area.id` |
| `category_id` | bigint | no | FK → `offers_offercategory.id` |
| `user_id` | char(32) | no | unique, FK → `accounts_user.id` |
| `verified_by_id` | char(32) | yes | FK → `accounts_user.id` |

Composite indexes: `(area_id,status)`

### `merchants_merchantdocument`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `doc_type` | varchar(30) | no |  |
| `file` | varchar(100) | no |  |
| `merchant_id` | bigint | no | FK → `merchants_merchant.id` |
| `uploaded_by_id` | char(32) | no | FK → `accounts_user.id` |

### `merchants_merchantverification`

Append-only evidence record for each verification pass. Merchant.status reflects the current outcome; this table is the audit trail behind it — per spec, verification must never be a bare `verified=True` flag.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `outcome` | varchar(20) | no |  |
| `checklist` | json | no |  |
| `notes` | longtext | no |  |
| `merchant_id` | bigint | no | FK → `merchants_merchant.id` |
| `performed_by_id` | char(32) | no | FK → `accounts_user.id` |

<a id="offers"></a>
## Offers, categories & interactions

### `offers_offer`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `item_name` | varchar(150) | no |  |
| `normal_price` | decimal(12,2) | no |  |
| `member_price` | decimal(12,2) | no |  |
| `quantity` | int unsigned | no |  |
| `pickup_location` | varchar(255) | no |  |
| `delivery_available` | tinyint(1) | no |  |
| `offer_radius_km` | decimal(5,2) | yes |  |
| `packaging_status` | varchar(20) | no |  |
| `status` | varchar(20) | no |  |
| `visibility_score` | int unsigned | no |  |
| `views_count` | int unsigned | no |  |
| `expires_at` | datetime(6) | no |  |
| `area_id` | bigint | no | FK → `core_area.id` |
| `merchant_id` | bigint | no | FK → `merchants_merchant.id` |
| `category_id` | bigint | no | FK → `offers_offercategory.id` |

Composite indexes: `(area_id,category_id,status)`; `(status,expires_at)`

### `offers_offercategory`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `key` | varchar(50) | no | unique |
| `label` | varchar(100) | no |  |
| `emoji` | varchar(8) | no |  |
| `is_active` | tinyint(1) | no |  |

### `offers_offerimage`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `image` | varchar(100) | no |  |
| `is_primary` | tinyint(1) | no |  |
| `offer_id` | bigint | no | FK → `offers_offer.id` |

### `offers_offerinteraction`

Real interaction tracking so merchant/admin stats (views, calls, WhatsApp clicks, delivery-request clicks) come from the database instead of a static counter — see spec section 64 (dashboard stats must all be DB-derived).

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `kind` | varchar(30) | no |  |
| `offer_id` | bigint | no | FK → `offers_offer.id` |
| `user_id` | char(32) | yes | FK → `accounts_user.id` |

Composite indexes: `(offer_id,kind,created_at)`

<a id="claims"></a>
## Claim codes & redemptions

### `claims_claimevent`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `event_type` | varchar(50) | no |  |
| `metadata` | json | no |  |
| `actor_id` | char(32) | yes | FK → `accounts_user.id` |
| `claim_id` | bigint | no | FK → `claims_offerclaim.id` |

### `claims_offerclaim`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `code` | varchar(16) | no | unique |
| `status` | varchar(20) | no |  |
| `expected_saving` | decimal(12,2) | no |  |
| `expires_at` | datetime(6) | no |  |
| `redeemed_at` | datetime(6) | yes |  |
| `redemption_attempts` | smallint unsigned | no |  |
| `member_id` | bigint | no | FK → `members_member.id` |
| `offer_id` | bigint | no | FK → `offers_offer.id` |
| `redeemed_by_id` | char(32) | yes | FK → `accounts_user.id` |

Composite indexes: `(member_id,status)`; `(status,expires_at)`

<a id="savings"></a>
## Savings records

### `savings_savingsrecord`

One row per successfully redeemed claim. This — not a running balance field anywhere — is the source of truth for a member's confirmed savings; dashboard totals are always computed by aggregating these rows, never stored/incremented directly (see savings/selectors.py).

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `normal_price` | decimal(12,2) | no |  |
| `member_price` | decimal(12,2) | no |  |
| `saving_amount` | decimal(12,2) | no |  |
| `claim_id` | bigint | no | unique, FK → `claims_offerclaim.id` |
| `member_id` | bigint | no | FK → `members_member.id` |
| `merchant_id` | bigint | no | FK → `merchants_merchant.id` |

Composite indexes: `(member_id,created_at)`

<a id="item_requests"></a>
## Item requests

### `item_requests_memberrequest`

A member asking for an item they haven't found on the platform — merchants browse open requests in their area and respond with availability/pricing, rather than the member searching existing offers (spec's ITEM REQUESTS feature).

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `item_name` | varchar(150) | no |  |
| `description` | longtext | no |  |
| `max_budget` | decimal(12,2) | yes |  |
| `status` | varchar(20) | no |  |
| `area_id` | bigint | no | FK → `core_area.id` |
| `member_id` | bigint | no | FK → `members_member.id` |
| `fulfilled_response_id` | bigint | yes | FK → `item_requests_requestresponse.id` |

Composite indexes: `(area_id,status)`; `(member_id,status)`

### `item_requests_requestresponse`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `message` | longtext | no |  |
| `price` | decimal(12,2) | yes |  |
| `merchant_id` | bigint | no | FK → `merchants_merchant.id` |
| `request_id` | bigint | no | FK → `item_requests_memberrequest.id` |

Composite indexes: `(request_id,merchant_id)` unique

<a id="deliveries"></a>
## Deliveries, routes & pickup points

### `deliveries_deliveryjob`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `dropoff_address` | varchar(255) | no |  |
| `delivery_type` | varchar(20) | no |  |
| `fare` | decimal(10,2) | no |  |
| `status` | varchar(30) | no |  |
| `assigned_at` | datetime(6) | yes |  |
| `picked_up_at` | datetime(6) | yes |  |
| `delivered_at` | datetime(6) | yes |  |
| `failed_at` | datetime(6) | yes |  |
| `failure_reason` | varchar(255) | no |  |
| `claim_id` | bigint | yes | unique, FK → `claims_offerclaim.id` |
| `dropoff_area_id` | bigint | no | FK → `core_area.id` |
| `pickup_merchant_id` | bigint | no | FK → `merchants_merchant.id` |
| `rider_id` | bigint | yes | FK → `riders_rider.id` |
| `route_id` | bigint | yes | FK → `deliveries_sharedroute.id` |

Composite indexes: `(rider_id,status)`; `(status,dropoff_area_id)`

### `deliveries_deliveryotp`

Customer hands the rider this code on delivery. Hashed at rest, same pattern as accounts.PhoneVerification — never store the raw code.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `code_hash` | varchar(64) | no |  |
| `attempts` | smallint unsigned | no |  |
| `max_attempts` | smallint unsigned | no |  |
| `is_used` | tinyint(1) | no |  |
| `expires_at` | datetime(6) | no |  |
| `job_id` | bigint | no | unique, FK → `deliveries_deliveryjob.id` |

### `deliveries_deliverystatushistory`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `from_status` | varchar(30) | no |  |
| `to_status` | varchar(30) | no |  |
| `notes` | varchar(255) | no |  |
| `changed_by_id` | char(32) | yes | FK → `accounts_user.id` |
| `job_id` | bigint | no | FK → `deliveries_deliveryjob.id` |

### `deliveries_pickuppoint`

A staffed collection/drop-off spot (shop, fuel station, agent kiosk) where parcels can be left for members instead of door delivery.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `name` | varchar(150) | no |  |
| `address` | varchar(255) | no |  |
| `contact_phone` | varchar(20) | no |  |
| `opening_hours` | varchar(120) | no |  |
| `is_active` | tinyint(1) | no |  |
| `area_id` | bigint | no | FK → `core_area.id` |
| `created_by_id` | char(32) | yes | FK → `accounts_user.id` |

### `deliveries_riderearning`

One row per completed delivery. Commission is calculated server-side from core.SystemSetting at delivery-completion time — never hard-coded, never trusted from the client.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `gross_amount` | decimal(10,2) | no |  |
| `commission_amount` | decimal(10,2) | no |  |
| `net_amount` | decimal(10,2) | no |  |
| `delivery_job_id` | bigint | no | unique, FK → `deliveries_deliveryjob.id` |
| `rider_id` | bigint | no | FK → `riders_rider.id` |

### `deliveries_sharedroute`

A rider's declared trip (area A -> area B, at roughly a given time) that multiple shared_route DeliveryJobs can attach to — the grouping layer the spec calls SharedRoute/RoutePackage. Individual DeliveryJobs keep their own full state machine unchanged (see below); a route is a visibility/capacity construct on top, not a replacement for per-job tracking. Commission math is untouched — it's still computed per job from delivery_type, exactly as before this model existed.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `departure_time` | datetime(6) | no |  |
| `max_packages` | smallint unsigned | no |  |
| `status` | varchar(20) | no |  |
| `destination_area_id` | bigint | no | FK → `core_area.id` |
| `origin_area_id` | bigint | no | FK → `core_area.id` |
| `rider_id` | bigint | no | FK → `riders_rider.id` |

Composite indexes: `(status,origin_area_id,destination_area_id)`

<a id="riders"></a>
## Riders

### `riders_rider`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `vehicle_type` | varchar(20) | no |  |
| `plate_number` | varchar(30) | no |  |
| `status` | varchar(20) | no |  |
| `verified_at` | datetime(6) | yes |  |
| `is_available` | tinyint(1) | no |  |
| `area_id` | bigint | no | FK → `core_area.id` |
| `user_id` | char(32) | no | unique, FK → `accounts_user.id` |
| `verified_by_id` | char(32) | yes | FK → `accounts_user.id` |

Composite indexes: `(area_id,status,is_available)`

### `riders_riderdocument`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `doc_type` | varchar(30) | no |  |
| `file` | varchar(100) | no |  |
| `rider_id` | bigint | no | FK → `riders_rider.id` |
| `uploaded_by_id` | char(32) | no | FK → `accounts_user.id` |

### `riders_riderverification`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `outcome` | varchar(20) | no |  |
| `checklist` | json | no |  |
| `notes` | longtext | no |  |
| `performed_by_id` | char(32) | no | FK → `accounts_user.id` |
| `rider_id` | bigint | no | FK → `riders_rider.id` |

<a id="agents"></a>
## Agents, prices & tasks

### `agents_agent`

Agents are onboarded directly by an admin (agent_manage capability) rather than through a public application/verification flow like merchants and riders — there's no AgentVerification model for that reason; if a public agent-application flow is needed later it can be added the same way merchants/riders work.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `status` | varchar(20) | no |  |
| `user_id` | char(32) | no | unique, FK → `accounts_user.id` |

### `agents_agent_areas`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `agent_id` | bigint | no | FK → `agents_agent.id` |
| `area_id` | bigint | no | FK → `core_area.id` |

Composite indexes: `(agent_id,area_id)` unique

### `agents_agentearning`

Credited when an agent completes a merchant/rider verification. Fee amounts are configurable via core.SystemSetting, never hard-coded.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `source` | varchar(30) | no |  |
| `amount` | decimal(10,2) | no |  |
| `reference` | varchar(100) | no |  |
| `agent_id` | bigint | no | FK → `agents_agent.id` |

### `agents_agenttask`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `kind` | varchar(30) | no |  |
| `title` | varchar(150) | no |  |
| `description` | longtext | no |  |
| `due_at` | datetime(6) | yes |  |
| `status` | varchar(20) | no |  |
| `completed_at` | datetime(6) | yes |  |
| `agent_id` | bigint | no | FK → `agents_agent.id` |
| `area_id` | bigint | yes | FK → `core_area.id` |
| `created_by_id` | char(32) | yes | FK → `accounts_user.id` |

### `agents_pricerecord`

A price an agent physically observed in the field — feeds the price-comparison feature (spec section 62) with real, sourced data rather than merchant self-reported prices alone.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `item_name` | varchar(150) | no |  |
| `price` | decimal(12,2) | no |  |
| `agent_id` | bigint | no | FK → `agents_agent.id` |
| `area_id` | bigint | no | FK → `core_area.id` |
| `category_id` | bigint | no | FK → `offers_offercategory.id` |

Composite indexes: `(area_id,category_id,created_at)`

<a id="complaints"></a>
## Complaints

### `complaints_complaint`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `subject` | varchar(200) | no |  |
| `description` | longtext | no |  |
| `status` | varchar(20) | no |  |
| `area_id` | bigint | no | FK → `core_area.id` |
| `assigned_agent_id` | bigint | yes | FK → `agents_agent.id` |
| `member_id` | bigint | no | FK → `members_member.id` |

Composite indexes: `(area_id,status)`; `(assigned_agent_id,status)`

### `complaints_complaintmessage`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `message` | longtext | no |  |
| `complaint_id` | bigint | no | FK → `complaints_complaint.id` |
| `sender_id` | char(32) | no | FK → `accounts_user.id` |

### `complaints_complaintresolution`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `resolution_note` | longtext | no |  |
| `complaint_id` | bigint | no | unique, FK → `complaints_complaint.id` |
| `resolved_by_id` | char(32) | no | FK → `accounts_user.id` |

<a id="payments"></a>
## Payments & withdrawals (ioTec)

### `payments_ledgerentry`

Every confirmed financial movement gets one immutable row here — never just `balance += amount`. This is a single-entry record per payment for now (suffices to prove 'money moved, here's proof'); a full double-entry chart of accounts (platform revenue, rider payables, settlement batches) is its own later phase once disbursements/settlements exist to reconcile against.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `direction` | varchar(10) | no |  |
| `amount` | decimal(12,2) | no |  |
| `fee` | decimal(12,2) | no |  |
| `net_amount` | decimal(12,2) | no |  |
| `reference` | varchar(100) | no |  |
| `user_id` | char(32) | no | FK → `accounts_user.id` |
| `payment_id` | bigint | yes | FK → `payments_payment.id` |

Composite indexes: `(user_id,created_at)`

### `payments_payment`

The provider-facing record for a single ioTec Pay collection attempt. `internal_reference` is what we send as ioTec's `externalId` — generated here, never accepted from the frontend. This is deliberately generic (`purpose` + a nullable link to whatever it's for) so card/mobile-money collection logic doesn't need to be duplicated per feature; subscriptions is the only purpose wired up so far, per spec section 10's unified /payments/initiate/ shape.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `purpose` | varchar(30) | no |  |
| `method` | varchar(20) | no |  |
| `amount` | decimal(12,2) | no |  |
| `currency` | varchar(3) | no |  |
| `internal_reference` | char(32) | no | unique |
| `provider` | varchar(30) | no |  |
| `provider_transaction_id` | varchar(100) | no |  |
| `payer_phone` | varchar(20) | no |  |
| `payer_email` | varchar(254) | no |  |
| `redirect_url` | varchar(200) | no |  |
| `status` | varchar(20) | no |  |
| `subscription_payment_id` | bigint | yes | unique, FK → `subscriptions_subscriptionpayment.id` |
| `user_id` | char(32) | no | FK → `accounts_user.id` |
| `promotion_purchase_id` | bigint | yes | unique, FK → `promotions_promotionpurchase.id` |

Composite indexes: `(status,created_at)`; `(user_id,status)`

### `payments_paymentcallback`

Immutable log of every callback ioTec sends us, processed or not — kept even for duplicates/invalid ones, since this table is the audit trail for 'what did the provider actually tell us and when'.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `raw_payload` | json | no |  |
| `provider_status` | varchar(50) | no |  |
| `processed` | tinyint(1) | no |  |
| `processing_notes` | varchar(255) | no |  |
| `payment_id` | bigint | yes | FK → `payments_payment.id` |
| `provider_transaction_id` | varchar(100) | no |  |

Composite indexes: `(payment_id,provider_status,provider_transaction_id)`

### `payments_withdrawal`

A disbursement request — rider (for now) cashing out earnings to mobile money. Funds are only ever considered available (see services/withdrawals.py) once counted against PENDING/PROCESSING/ COMPLETED withdrawals, so the same earnings can't be withdrawn twice while a request is in flight.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `source` | varchar(30) | no |  |
| `amount` | decimal(12,2) | no |  |
| `fee` | decimal(12,2) | no |  |
| `net_amount` | decimal(12,2) | no |  |
| `phone` | varchar(20) | no |  |
| `internal_reference` | char(32) | no | unique |
| `provider` | varchar(30) | no |  |
| `provider_transaction_id` | varchar(100) | no |  |
| `status` | varchar(20) | no |  |
| `completed_at` | datetime(6) | yes |  |
| `user_id` | char(32) | no | FK → `accounts_user.id` |

Composite indexes: `(status,created_at)`; `(user_id,status)`

### `payments_withdrawalcallback`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `raw_payload` | json | no |  |
| `provider_status` | varchar(50) | no |  |
| `provider_transaction_id` | varchar(100) | no |  |
| `processed` | tinyint(1) | no |  |
| `processing_notes` | varchar(255) | no |  |
| `withdrawal_id` | bigint | yes | FK → `payments_withdrawal.id` |

<a id="promotions"></a>
## Promotions

### `promotions_promotionpackage`

Admin-configurable — nothing about price/duration/boost is hard-coded. A merchant buys one of these to boost a specific offer's visibility_score for a fixed period.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `code` | varchar(30) | no | unique |
| `label` | varchar(100) | no |  |
| `price` | decimal(12,2) | no |  |
| `duration_days` | int unsigned | no |  |
| `visibility_boost` | int unsigned | no |  |
| `is_active` | tinyint(1) | no |  |

### `promotions_promotionpurchase`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `status` | varchar(20) | no |  |
| `starts_at` | datetime(6) | yes |  |
| `expires_at` | datetime(6) | yes |  |
| `merchant_id` | bigint | no | FK → `merchants_merchant.id` |
| `offer_id` | bigint | no | FK → `offers_offer.id` |
| `package_id` | bigint | no | FK → `promotions_promotionpackage.id` |

Composite indexes: `(status,expires_at)`

<a id="notifications"></a>
## Notifications

### `notifications_notification`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `category` | varchar(30) | no |  |
| `title` | varchar(150) | no |  |
| `message` | longtext | no |  |
| `is_read` | tinyint(1) | no |  |
| `metadata` | json | no |  |
| `user_id` | char(32) | no | FK → `accounts_user.id` |

Composite indexes: `(user_id,is_read,created_at)`

### `notifications_notificationpreference`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `created_at` | datetime(6) | no |  |
| `updated_at` | datetime(6) | no |  |
| `sms_enabled` | tinyint(1) | no |  |
| `email_enabled` | tinyint(1) | no |  |
| `in_app_enabled` | tinyint(1) | no |  |
| `user_id` | char(32) | no | unique, FK → `accounts_user.id` |

<a id="framework"></a>
## Django framework tables (auth, sessions, admin, migrations)

### `auth_group`

Groups are a generic way of categorizing users to apply permissions, or some other label, to those users. A user can belong to any number of groups.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | int | no | PK, auto |
| `name` | varchar(150) | no | unique |

### `auth_group_permissions`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `group_id` | int | no | FK → `auth_group.id` |
| `permission_id` | int | no | FK → `auth_permission.id` |

Composite indexes: `(group_id,permission_id)` unique

### `auth_permission`

The permissions system provides a way to assign permissions to specific users and groups of users.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | int | no | PK, auto |
| `name` | varchar(255) | no |  |
| `content_type_id` | int | no | FK → `django_content_type.id` |
| `codename` | varchar(100) | no |  |

Composite indexes: `(content_type_id,codename)` unique

### `django_admin_log`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | int | no | PK, auto |
| `action_time` | datetime(6) | no |  |
| `object_id` | longtext | yes |  |
| `object_repr` | varchar(200) | no |  |
| `action_flag` | smallint unsigned | no |  |
| `change_message` | longtext | no |  |
| `content_type_id` | int | yes | FK → `django_content_type.id` |
| `user_id` | char(32) | no | FK → `accounts_user.id` |

### `django_content_type`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | int | no | PK, auto |
| `app_label` | varchar(100) | no |  |
| `model` | varchar(100) | no |  |

Composite indexes: `(app_label,model)` unique

### `django_migrations`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | bigint | no | PK, auto |
| `app` | varchar(255) | no |  |
| `name` | varchar(255) | no |  |
| `applied` | datetime(6) | no |  |

### `django_session`

Django provides full support for anonymous sessions. The session framework lets you store and retrieve arbitrary data on a per-site-visitor basis. It stores data on the server side and abstracts the sending and receiving of cookies. Cookies contain a session ID -- not the data itself.

| Column | Type | Null | Notes |
|---|---|---|---|
| `session_key` | varchar(40) | no | PK |
| `session_data` | longtext | no |  |
| `expire_date` | datetime(6) | no |  |
