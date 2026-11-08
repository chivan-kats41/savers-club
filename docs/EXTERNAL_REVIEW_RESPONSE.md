# Response to an external review (each claim checked against the code and a test)

Verdict key: FALSE = the code already prevents it, and a test proves it · TRUE = reproduced, now fixed · BY DESIGN = true, a deliberate trade-off.

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | Delivery code never reaches the customer | FALSE (but see note) | `_send_delivery_code` texts it to the customer's phone at pickup; `DeliveryCodeTests.test_code_is_texted_to_the_customer…`. Note: if the SMS provider is down/unconfigured it was only logged, so a delivery could not complete. **Fixed:** the code now also appears in the customer's own account (in-app only, only in that failure case). |
| 2 | Wrong delivery codes roll back and are never counted | FALSE | `confirm_delivery` raises after the atomic block commits; `test_wrong_codes_are_counted_and_lock_the_code` |
| 3 | Payment/withdrawal rows vanish on an ioTec error | FALSE | records are committed BEFORE ioTec is called; an uncertain outcome stays PENDING and the balance stays reserved; `test_timeout_keeps_a_pending_record…`, `test_timeout_leaves_payment_pending…` |
| 4 | Client IP spoofable via X-Forwarded-For | FALSE | the RIGHT-most entry is used behind a trusted proxy; nginx overwrites the header; DRF `NUM_PROXIES` matches. `test_leftmost_forged_entry_is_not_trusted…`, `test_rotating_header_cannot_dodge_the_register_limit`, and (new) a DRF-throttle test |
| 5 | Reset codes are 4 digits with 5 fresh guesses per request | FALSE | 6 digits, 3 codes/hour/purpose, 5 guesses each; `test_codes_are_six_digits`, `test_issuing_is_capped_per_account` |
| 6 | Phone verification never enforced; numbers can be squatted | FALSE / residual | unverified users cannot sign in (`accounts/tests/test_security_batch.py`). Residual: a squatter can hold a number for up to 24 h (then it is released). |
| 7 | Claiming needs no subscription | FALSE | `REQUIRE_SUBSCRIPTION_TO_CLAIM` defaults ON (only the test settings turn it off); `test_claiming_needs_an_active_subscription`, `test_expired_subscription_cannot_claim` |
| 8 | Legacy `/member/subscription/renew/` blocks real payments | **TRUE, fixed** | reproduced: a real payment right after it failed with "already pending" for up to 15 min. **Fixed:** starting a real payment now closes such leftovers immediately. The `REQUIRES_REVIEW` half is FALSE (`test_payment_parked_for_review_does_not_block…`). |
| – | 500 on unknown offer / `"NaN"` withdrawal / code collisions | FALSE | 400s; 6-char codes (887M) with retry; `test_unknown_offer_is_a_400…`, `test_nan_and_garbage_amounts…`, `test_claim_code_collision_is_retried` |
| – | Registration not atomic | FALSE | `test_failed_member_creation_leaves_no_orphan_user` |
| – | Lockout lets anyone lock any account (incl. admin) | BY DESIGN | 5 failures/15 min per person; the cost is a 15-minute denial of service. Options in the reply. |
| – | TOTP plaintext/replayable; gate keyed on role | FALSE | Fernet-encrypted at rest, one use per time step, gate is `is_admin() or is_staff`; `test_secret_is_encrypted_at_rest…`, `test_a_code_can_only_be_used_once`, (new) staff-with-member-role test |
| – | Referral rewards never credited | FALSE | `credit_referral_rewards` runs hourly via Celery beat / `run_periodic` (so the scheduler must be running!); `test_reward_is_held_then_credited` |
| – | Delivery fares not collected / paid from your wallet | FALSE | cash fares are recorded as collected and subtracted from the rider's balance; `test_cash_delivery_does_not_pay_the_rider_the_fare_a_second_time` |
| – | Expired claim not restocked | FALSE | `test_expired_claim_is_restocked_when_the_merchant_tries_to_redeem_it` |
| – | Swagger/ReDoc public in production | FALSE | `ENABLE_API_DOCS` defaults off; `test_docs_are_not_exposed_unless_enabled` |
| – | nginx 10 req/min on auth | FALSE | `deploy/nginx.conf`: 30 r/m with burst 20 |
| – | Cache and Celery share a Redis DB; compose broker ignored | FALSE | cache DB 1, broker DB 0; `CELERY_BROKER_URL` is read in `config/settings/base.py` |

Not verifiable here: the real nginx you deploy, a live SMS/ioTec account, and MySQL row-locking (tests ran on SQLite).
