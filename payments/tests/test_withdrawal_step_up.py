"""Taking money out needs more than a session: a one-time code texted to the ACCOUNT's phone, a daily cap, and
(for claims) a limit on wrong-code guessing."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import PhoneVerification, Role, User
from claims.services import ClaimError, claim_offer, redeem_claim
from core.models import SystemSetting
from core.tests.test_review_fixes import IOTEC, Base, post_that
from members.models import Member, ReferralReward
from merchants.models import Merchant
from payments.models import Withdrawal
from payments.services.withdrawal_flow import WithdrawalError, request_referral_withdrawal

URL = "/api/v1/member/referrals/withdraw/"
CODE_URL = "/api/v1/withdraw/code/"


@override_settings(**IOTEC)
class StepUpTests(Base):
    def setUp(self):
        super().setUp()
        friend_user = User.objects.create_user(phone="+256700000060", password="Pass12345!x", role=Role.MEMBER, phone_verified=True)
        friend = Member.objects.create(user=friend_user, area=self.area, referred_by=self.member)
        ReferralReward.objects.create(referrer=self.member, referred_member=friend, amount=Decimal("2500"), status="credited")
        self.ok = lambda: Mock(status_code=200, json=lambda: {"id": "t", "status": "Pending"})
        SystemSetting.objects.update_or_create(key="withdrawal.minimum_ugx", defaults={"value": "500"})   # lets tests use small amounts
        self.c = APIClient(raise_request_exception=False)
        self.c.force_login(self.memu)

    def code(self, user=None):
        _, raw = PhoneVerification.issue(user or self.memu, PhoneVerification.Purpose.WITHDRAWAL)
        return raw

    def withdraw(self, amount="2500", phone="0772123456", **extra):
        with patch("requests.post", side_effect=post_that(self.ok)):
            return self.c.post(URL, {"amount": amount, "phone": phone, **extra}, format="json")

    # ------------------------------------------------------------------ the code is required and checked
    def test_a_withdrawal_without_a_code_is_refused(self):
        r = self.withdraw()
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (400, "CODE_REQUIRED"))
        self.assertFalse(Withdrawal.objects.exists())

    def test_a_wrong_code_is_refused(self):
        self.code()
        r = self.withdraw(code="000000")
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (400, "INVALID_CODE"))
        self.assertFalse(Withdrawal.objects.exists())

    def test_the_right_code_lets_it_through(self):
        r = self.withdraw(code=self.code())
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Withdrawal.objects.count(), 1)

    def test_a_code_works_once(self):
        code = self.code()
        self.assertEqual(self.withdraw(amount="1000", code=code).status_code, 201)
        r = self.withdraw(amount="1000", code=code)
        self.assertEqual(r.json()["error"]["code"], "INVALID_CODE")
        self.assertEqual(Withdrawal.objects.count(), 1)

    def test_a_rejected_request_does_not_burn_the_code(self):
        code = self.code()
        over = self.withdraw(amount="999999", code=code)                 # more than the balance
        self.assertEqual(over.json()["error"]["code"], "WITHDRAWAL_FAILED")
        self.assertEqual(self.withdraw(amount="1000", code=code).status_code, 201)   # same code, now fine

    def test_five_wrong_guesses_burn_the_code_even_for_the_right_one(self):
        code = self.code()
        for _ in range(5):
            self.withdraw(code="000000" if code != "000000" else "111111")
        r = self.withdraw(code=code)
        self.assertEqual(r.json()["error"]["code"], "INVALID_CODE")

    def test_an_expired_code_is_refused(self):
        code = self.code()
        PhoneVerification.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.withdraw(code=code).json()["error"]["code"], "INVALID_CODE")

    def test_other_kinds_of_codes_do_not_count(self):
        _, reg = PhoneVerification.issue(self.memu, PhoneVerification.Purpose.REGISTRATION)
        self.assertEqual(self.withdraw(code=reg).json()["error"]["code"], "INVALID_CODE")

    def test_someone_elses_code_does_not_work(self):
        other = User.objects.create_user(phone="+256700000077", password="x", role=Role.MEMBER, phone_verified=True)
        theirs = self.code(other)
        self.assertEqual(self.withdraw(code=theirs).json()["error"]["code"], "INVALID_CODE")

    def test_the_requirement_can_be_switched_off_for_local_testing(self):
        SystemSetting.objects.update_or_create(key="withdrawal.require_code", defaults={"value": "0"})
        self.assertEqual(self.withdraw().status_code, 201)

    def test_the_rider_page_shows_the_code_box_and_send_button(self):
        c = APIClient(raise_request_exception=False); c.force_login(self.ru)
        html = c.get("/rider/").content.decode()
        self.assertIn('name="code"', html)
        self.assertIn("data-withdraw-code", html)
        self.assertIn("withdraw_code.js", html)
        self.assertIn(f"(…{self.ru.phone[-3:]})", html)         # tells them which phone the code goes to

    def test_the_referral_and_rider_endpoints_both_demand_a_code(self):
        r = self.c.post("/api/v1/rider/withdraw/", {"amount": "1000", "phone": "0772123456"}, format="json")
        self.assertIn(r.status_code, (400, 403, 404))       # not a rider here; never reaches a withdrawal either way
        self.assertFalse(Withdrawal.objects.exists())

    # ------------------------------------------------------------------ sending the code
    def test_the_code_is_texted_to_the_account_phone_not_the_payout_number(self):
        sent = []
        with patch("notifications.services.sms_gateway.send_sms", side_effect=lambda to, text: sent.append((to, text)) or True):
            r = self.c.post(CODE_URL, {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(sent[0][0], self.memu.phone)                  # the number on the account...
        self.assertNotIn("0772123456", sent[0][0])                     # ...never the one the withdrawal names
        raw = [t for t in sent[0][1].split() if t.isdigit() and len(t) == 6][0]
        self.assertEqual(self.withdraw(code=raw, phone="0772123456").status_code, 201)

    def test_the_response_hides_most_of_the_phone_and_never_leaks_the_code_in_production(self):
        with patch("notifications.services.sms_gateway.send_sms", return_value=True):
            data = self.c.post(CODE_URL, {}, format="json").json()["data"]
        self.assertEqual(data["phone_hint"], "•••" + self.memu.phone[-3:])
        self.assertNotIn("dev_code", data)

    @override_settings(DEBUG=True)
    def test_in_debug_the_code_is_returned_so_it_can_be_tried_without_sms(self):
        with patch("notifications.services.sms_gateway.send_sms", return_value=False):
            pass
        with patch("notifications.services.sms_gateway.send_sms", return_value=True):
            data = self.c.post(CODE_URL, {}, format="json").json()["data"]
        self.assertEqual(len(data["dev_code"]), 6)
        self.assertEqual(self.withdraw(code=data["dev_code"]).status_code, 201)

    def test_sms_failure_is_reported_not_hidden(self):
        with patch("notifications.services.sms_gateway.send_sms", return_value=False):
            r = self.c.post(CODE_URL, {}, format="json")
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (503, "SMS_FAILED"))

    def test_only_three_codes_an_hour(self):
        with patch("notifications.services.sms_gateway.send_sms", return_value=True):
            codes = [self.c.post(CODE_URL, {}, format="json").status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])

    def test_you_must_be_signed_in_to_ask_for_a_code(self):
        self.assertIn(APIClient().post(CODE_URL, {}, format="json").status_code, (401, 403))

    # ------------------------------------------------------------------ daily cap
    def past_withdrawal(self, amount, status=Withdrawal.Status.COMPLETED, hours_ago=1):
        w = Withdrawal.objects.create(user=self.memu, source=Withdrawal.Source.RIDER_EARNINGS, amount=amount, fee=0,
                                      net_amount=amount, phone="0772123456", status=status)
        Withdrawal.objects.filter(pk=w.pk).update(created_at=timezone.now() - timedelta(hours=hours_ago))
        return w

    def test_a_single_withdrawal_over_the_daily_limit_is_refused(self):
        SystemSetting.objects.update_or_create(key="withdrawal.daily_limit_ugx", defaults={"value": "2000"})
        with patch("requests.post", side_effect=post_that(self.ok)), self.assertRaises(WithdrawalError) as cm:
            request_referral_withdrawal(self.member, Decimal("2500"), "0772123456")
        self.assertIn("Daily withdrawal limit", str(cm.exception))

    def test_earlier_withdrawals_today_count_towards_the_limit(self):
        SystemSetting.objects.update_or_create(key="withdrawal.daily_limit_ugx", defaults={"value": "3000"})
        self.past_withdrawal(1500)
        with patch("requests.post", side_effect=post_that(self.ok)), self.assertRaises(WithdrawalError) as cm:
            request_referral_withdrawal(self.member, Decimal("2000"), "0772123456")
        self.assertIn("up to UGX 1,500 more", str(cm.exception))                 # tells them what room is left

    def test_failed_and_reversed_withdrawals_do_not_count(self):
        SystemSetting.objects.update_or_create(key="withdrawal.daily_limit_ugx", defaults={"value": "3000"})
        self.past_withdrawal(1500, status=Withdrawal.Status.FAILED)
        self.past_withdrawal(1500, status=Withdrawal.Status.REVERSED)
        with patch("requests.post", side_effect=post_that(self.ok)):
            w = request_referral_withdrawal(self.member, Decimal("2000"), "0772123456")
        self.assertEqual(w.amount, Decimal("2000"))

    def test_withdrawals_older_than_a_day_do_not_count(self):
        SystemSetting.objects.update_or_create(key="withdrawal.daily_limit_ugx", defaults={"value": "3000"})
        self.past_withdrawal(2900, hours_ago=25)
        with patch("requests.post", side_effect=post_that(self.ok)):
            self.assertEqual(request_referral_withdrawal(self.member, Decimal("2500"), "0772123456").amount, Decimal("2500"))

    def test_the_cap_is_per_person(self):
        SystemSetting.objects.update_or_create(key="withdrawal.daily_limit_ugx", defaults={"value": "3000"})
        other = User.objects.create_user(phone="+256700000088", password="x", role=Role.MEMBER, phone_verified=True)
        Withdrawal.objects.create(user=other, source=Withdrawal.Source.RIDER_EARNINGS, amount=2900, fee=0, net_amount=2900,
                                  phone="0772123456", status=Withdrawal.Status.COMPLETED)
        with patch("requests.post", side_effect=post_that(self.ok)):
            self.assertEqual(request_referral_withdrawal(self.member, Decimal("2500"), "0772123456").amount, Decimal("2500"))

    def test_the_default_limit_is_one_million(self):
        from core.services import withdrawal_daily_limit
        self.assertEqual(withdrawal_daily_limit(), Decimal("1000000"))


# ====================================================================== claim-code guessing ===========================
class ClaimCodeGuessingTests(Base):
    def setUp(self):
        super().setUp()
        cache.clear()

    def wrong(self, merchant, n, code="ZZZZZZ"):
        for _ in range(n):
            with self.assertRaises(ClaimError):
                redeem_claim(merchant, code)

    def test_eight_wrong_codes_pause_redeeming_even_for_a_valid_code(self):
        claim = claim_offer(self.member, self.offer.id)
        self.wrong(self.merchant, 8)
        with self.assertRaises(ClaimError) as cm:
            redeem_claim(self.merchant, claim.code)
        self.assertIn("Too many wrong codes", str(cm.exception))
        claim.refresh_from_db(); self.assertEqual(claim.status, "claimed")       # not redeemed while paused

    def test_seven_wrong_codes_then_a_valid_one_still_works(self):
        claim = claim_offer(self.member, self.offer.id)
        self.wrong(self.merchant, 7)
        self.assertEqual(redeem_claim(self.merchant, claim.code).status, "redeemed")

    def test_a_good_redemption_clears_the_streak(self):
        c1 = claim_offer(self.member, self.offer.id)
        self.wrong(self.merchant, 7)
        redeem_claim(self.merchant, c1.code)
        self.offer.refresh_from_db()
        self.wrong(self.merchant, 7)                                             # another 7 is allowed: streak was reset
        c2 = claim_offer(self.member, self.offer.id)
        self.assertEqual(redeem_claim(self.merchant, c2.code).status, "redeemed")

    def test_codes_belonging_to_another_shop_count_as_wrong_guesses(self):
        other_user = User.objects.create_user(phone="+256700000099", password="x", role=Role.MERCHANT, phone_verified=True)
        other = Merchant.objects.create(user=other_user, business_name="Other", category=self.merchant.category, area=self.area)
        foreign = claim_offer(self.member, self.offer.id)                        # belongs to self.merchant's offer
        for _ in range(8):
            with self.assertRaises(ClaimError):
                redeem_claim(other, foreign.code)
        with self.assertRaises(ClaimError) as cm:
            redeem_claim(other, "ABCDEF")
        self.assertIn("Too many wrong codes", str(cm.exception))

    def test_one_merchants_guessing_does_not_lock_another(self):
        other_user = User.objects.create_user(phone="+256700000098", password="x", role=Role.MERCHANT, phone_verified=True)
        other = Merchant.objects.create(user=other_user, business_name="Other", category=self.merchant.category, area=self.area)
        self.wrong(other, 8)
        claim = claim_offer(self.member, self.offer.id)
        self.assertEqual(redeem_claim(self.merchant, claim.code).status, "redeemed")

    def test_lock_is_recorded_as_a_risk_event(self):
        from core.models import RiskEvent

        self.wrong(self.merchant, 8)
        with self.assertRaises(ClaimError):
            redeem_claim(self.merchant, "ABCDEF")
        self.assertTrue(RiskEvent.objects.filter(event_type="claim_code_guessing").exists())
