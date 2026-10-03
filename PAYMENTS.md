# Payments (ioTec Pay: mobile money + cards)

Built from the ioTec Pay v1 OpenAPI spec. Tests mock the HTTP layer; **run `python manage.py iotec_check` with your
real credentials first** (it moves no money), then make one small real payment in the sandbox/live wallet.

## 1. Configure (`.env`)

```
IOTEC_BASE_URL=https://pay.iotec.io
IOTEC_API_KEY=            # portal: API key    (OAuth client id)
IOTEC_SECRET_KEY=         # portal: Secret key (OAuth client secret)
IOTEC_WALLET_ID=          # the wallet money is collected into / paid out of
IOTEC_CURRENCY=UGX
IOTEC_CHARGES_CATEGORY=   # "", ChargeCustomer or ChargeWallet (who pays ioTec's fee)
IOTECH_CALLBACK_URL=https://YOUR-DOMAIN/api/iotec/callback
IOTEC_CALLBACK_SECRET=    # random value you choose; also set as the callback "Security Header" in the portal
SITE_URL=https://YOUR-DOMAIN
```

`settings.PAYMENT_PROVIDERS["IOTECH_PAY"]` exposes the same values in the usual dict form. The older names
`IOTEC_CLIENT_ID` / `IOTEC_CLIENT_SECRET` still work.

**Register ONE callback URL in the ioTec portal** (Wallet > Settings > Callback URLs): `https://YOUR-DOMAIN/api/iotec/callback`.
It handles both money-in and money-out events. The API has no per-request callback field, so the URL lives in the portal.
Set the Security Header there to the same value as `IOTEC_CALLBACK_SECRET`; we accept it as `X-Callback-Secret: <value>`
or `Authorization: Bearer <value>`. A localhost URL cannot receive callbacks: locally, payments still complete because the
status endpoint and the 5-minute reconciliation job ask ioTec directly.

## 2. How a payment flows

**Mobile money (MTN/Airtel)**: `POST /api/v1/payments/initiate/` -> we call `POST /api/collections/collect` ->
the payer gets a prompt on their phone -> the page polls our status endpoint until it settles. The number can be
typed as `+2567…`, `07…` or `7…`; it is sent as `2567XXXXXXXX`.

**Card (Visa/Mastercard)**: same endpoint with `"method": "card"` -> we call `POST /api/collections/collect/card`
(payer = the customer's **email**; falls back to the account email) -> response contains `cardRedirectUrl` -> the browser
is redirected there (ioTec's hosted PegPay page; **card details never touch our servers**) -> afterwards PegPay sends the
customer to `SITE_URL/payments/return/?ref=<our reference>` (only if `SITE_URL` is https; otherwise ioTec shows its own
page and the payment still completes). That page ignores anything in the query string and asks our server, which asks ioTec.

**Withdrawals (riders)**: `POST /api/disbursements/disburse` (`category=MobileMoney`, numeric `amount` >= 500).

## 3. What decides that a payment succeeded

Only ioTec's own status API, never the callback body, the browser or the return URL:
- callbacks only *locate* the payment; the status applied is fetched from `GET /api/collections/status/{id}`
  (or `/external-id/{externalId}` if the initiation response was lost);
- `Success` for a different amount or currency than we asked for => `REQUIRES_REVIEW`, nothing is activated;
- `Failed`, `RolledBack`, `Cancelled`, `Rejected` => failed; `Pending`, `AwaitingApproval`, `Scheduled`, `SentToVendor`
  or anything unknown => keep waiting (never credit or fail on a status we don't recognise);
- the status endpoint checks ioTec at most once every 4 s per payment; a Celery beat job reconciles open payments
  (pending **and** sent-to-vendor) every 5 minutes. On Windows without Celery run `python manage.py reconcile_payments`.

## 4. Operations

```
python manage.py iotec_check        # credentials, wallet id + balance, callback/secret/SITE_URL: no money moves
python manage.py reconcile_payments # settle anything stuck right now
```
The admin console > Payments page shows the live wallet balance (withdrawals fail when it runs out).

## 5. Limits and notes
- ioTec minimum: UGX 500 per collection/disbursement (validated before calling the API).
- Currencies accepted by the API: UGX, USD, ITX. We use `IOTEC_CURRENCY`.
- There is no refund endpoint; refund by disbursing back to the payer.
- Subscriptions and promotions are the supported collection purposes today; withdrawals are for rider earnings.
- Rotate the API/secret keys in the ioTec portal if they were ever pasted into chat, email or git.
