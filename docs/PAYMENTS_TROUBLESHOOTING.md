# A payment stays "pending"

**Why it happens.** Only two things can settle a mobile-money payment: ioTec's *callback* to your server, or *your server asking
ioTec* (the reconcile sweep / the status endpoint). On a local machine (`127.0.0.1`) ioTec cannot call you back, and if nothing is
running the sweep, nobody ever asks. The payment then sits in `sent_to_vendor` forever.

**Settle it now**
1. `python manage.py reconcile_payments` : asks ioTec about every open payment and prints each one, e.g.
   `payment #3 (01a11903…): sent_to_vendor -> success`. A line ending in *could not reach/authenticate with ioTec* means your
   `IOTEC_*` settings are wrong or ioTec is down: run `python manage.py iotec_check` and read `logs/payments.log`.
2. Or just open `/member/`: the banner now asks ioTec by itself on load and every few seconds, and has a **Check status** button.

**Keep it settling**
- Local development: run `python manage.py run_periodic` in a second terminal (it runs `reconcile_payments` every 5 minutes), or
  keep Celery beat running.
- Production: give ioTec a public HTTPS callback URL and set `IOTEC_CALLBACK_SECRET`; keep the sweep scheduled as a safety net.

**What the system does with an unanswered payment**
- Within 30 minutes the banner says "approve it on your phone". After that it says it could not confirm the payment yet, with a Check
  status button (it no longer claims to be waiting for a prompt that expired days ago).
- After `payment.reconciliation_timeout_minutes` (60) with no answer the payment is parked as *requires review*, but it is **still
  re-checked for 14 days**: a late approval activates the subscription, a late failure releases the member. Nothing is ever guessed.
- A "Success" for a different amount is never credited; it stays parked and is reported once, not every sweep.
- Don't pay again while a payment is unresolved: if ioTec later reports success the subscription activates by itself.
