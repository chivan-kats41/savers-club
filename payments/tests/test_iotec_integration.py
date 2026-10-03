"""ioTec Pay integration, checked against the v1 OpenAPI spec: request bodies, card flow, status handling,
the single callback URL, on-demand verification and the card return page. No real network calls."""
import json
from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Role, User
from core.models import Area
from members.models import Member
from payments import config
from payments.models import Payment, Withdrawal
from payments.services import status as pstatus
from payments.services.iotec_client import IotecPayError
from payments.services.iotec_collections import initiate_card_collection, initiate_mobile_money_collection
from payments.services.iotec_disbursements import initiate_disbursement
from payments.services.reconciliation import reconcile_payment
from subscriptions.models import SubscriptionPlan

CFG = dict(IOTEC_CLIENT_ID="key", IOTEC_CLIENT_SECRET="secret", IOTEC_WALLET_ID="wallet-uuid",
           IOTEC_BASE_URL="https://pay.iotec.io", IOTEC_TOKEN_URL="https://id.iotec.io/connect/token",
           IOTEC_CURRENCY="UGX", IOTEC_CHARGES_CATEGORY="", SITE_URL="")


def ok_json(body, status=200):
    return Mock(status_code=status, json=lambda: body)


def post_router(responses):
    """requests.post stub: token URL -> token; other URLs looked up by suffix in `responses`."""
    calls = []

    def _post(url, *a, **kw):
        calls.append((url, kw.get("json")))
        if url.endswith("/connect/token"):
            return ok_json({"access_token": "tok", "expires_in": 300})
        for suffix, resp in responses.items():
            if url.endswith(suffix):
                return resp
        raise AssertionError(f"unexpected POST {url}")

    _post.calls = calls
    return _post


class Base(TestCase):
    def setUp(self):
        cache.clear()
        area = Area.objects.create(name="Testville")
        SubscriptionPlan.objects.create(code="1k-monthly", label="Monthly", price=1000, period_days=30)
        self.user = User.objects.create_user(phone="+256701000000", password="pass12345", role=Role.MEMBER,
                                             first_name="Amina", last_name="K", email="amina@example.com")
        self.member = Member.objects.create(user=self.user, area=area)

    def payment(self, method=Payment.Method.MOBILE_MONEY, amount=1000, **kw):
        kw.setdefault("payer_phone", "0701000000")
        kw.setdefault("payer_email", "amina@example.com")
        return Payment.objects.create(purpose=Payment.Purpose.SUBSCRIPTION, user=self.user, method=method,
                                      amount=amount, **kw)


@override_settings(**CFG)
class RequestBodyTests(Base):
    def test_mobile_money_body_matches_spec(self):
        router = post_router({"/api/collections/collect": ok_json({"id": "tx-1", "status": "Pending"})})
        pay = self.payment()
        with patch("requests.post", side_effect=router):
            initiate_mobile_money_collection(pay)
        url, body = router.calls[-1]
        self.assertEqual(url, "https://pay.iotec.io/api/collections/collect")
        self.assertEqual(body["category"], "MobileMoney")
        self.assertEqual(body["amount"], 1000.0)                 # required by the API
        self.assertEqual(body["currency"], "UGX")
        self.assertEqual(body["walletId"], "wallet-uuid")
        self.assertEqual(body["payer"], "256701000000")          # 256XXXXXXXXX
        self.assertEqual(body["externalId"], str(pay.internal_reference))
        self.assertLessEqual(len(body["payerNote"]), 100)
        self.assertLessEqual(len(body["payeeNote"]), 100)
        self.assertNotIn("transactionChargesCategory", body)     # default: ioTec decides

    def test_phone_formats_are_normalised_and_junk_rejected(self):
        for raw in ("+256701000000", "0701000000", "701000000", "256701000000", "+256 701-000 000"):
            self.assertEqual(config.normalize_msisdn(raw), "256701000000", raw)
        for bad in ("", "abc", "0201000000", "+254701000000", "07010", "0701000000; drop"):
            self.assertIsNone(config.normalize_msisdn(bad), bad)
        pay = self.payment(payer_phone="not-a-phone")
        with patch("requests.post") as post, self.assertRaises(IotecPayError):
            initiate_mobile_money_collection(pay)
        post.assert_not_called()                                 # never sends garbage to the provider

    def test_below_ioTec_minimum_is_refused_locally(self):
        pay = self.payment(amount=400)
        with patch("requests.post") as post, self.assertRaises(IotecPayError) as cm:
            initiate_mobile_money_collection(pay)
        self.assertIn("500", str(cm.exception))
        post.assert_not_called()

    @override_settings(IOTEC_CHARGES_CATEGORY="ChargeCustomer")
    def test_fee_payer_is_configurable_and_validated(self):
        router = post_router({"/api/collections/collect": ok_json({"id": "tx-1"})})
        with patch("requests.post", side_effect=router):
            initiate_mobile_money_collection(self.payment())
        self.assertEqual(router.calls[-1][1]["transactionChargesCategory"], "ChargeCustomer")
        with override_settings(IOTEC_CHARGES_CATEGORY="PayEveryone"):
            self.assertEqual(config.charges_category(), "")      # invalid value ignored, not sent

    def test_card_uses_card_endpoint_with_email_and_hosted_page(self):
        router = post_router({"/api/collections/collect/card": ok_json(
            {"id": "tx-9", "status": "Pending", "cardRedirectUrl": "https://pay.iotec.io/pegpay/abc"})})
        pay = self.payment(method=Payment.Method.CARD)
        with patch("requests.post", side_effect=router):
            initiate_card_collection(pay)
        url, body = router.calls[-1]
        self.assertEqual(url, "https://pay.iotec.io/api/collections/collect/card")
        self.assertEqual(body["category"], "Card")
        self.assertEqual(body["payer"], "amina@example.com")     # card payer is an EMAIL
        self.assertEqual(body["amount"], 1000.0)
        self.assertEqual(body["payerName"], "Amina K")
        self.assertNotIn("redirectUrl", body)                    # SITE_URL isn't https -> omitted (API needs https)
        pay.refresh_from_db()
        self.assertEqual(pay.redirect_url, "https://pay.iotec.io/pegpay/abc")
        self.assertEqual(pay.provider_transaction_id, "tx-9")
        self.assertNotIn("card", json.dumps(body).lower().replace('"category": "card"', ""))  # no card data fields

    @override_settings(SITE_URL="https://shop.example.com")
    def test_card_return_url_is_sent_when_site_is_https(self):
        router = post_router({"/api/collections/collect/card": ok_json({"id": "t", "cardRedirectUrl": "https://x/y"})})
        pay = self.payment(method=Payment.Method.CARD)
        with patch("requests.post", side_effect=router):
            initiate_card_collection(pay)
        self.assertEqual(router.calls[-1][1]["redirectUrl"], f"https://shop.example.com/payments/return/?ref={pay.internal_reference}")

    def test_card_errors(self):
        with patch("requests.post") as post, self.assertRaises(IotecPayError):
            initiate_card_collection(self.payment(method=Payment.Method.CARD, payer_email="nope"))
        post.assert_not_called()
        router = post_router({"/api/collections/collect/card": ok_json({"id": "t", "status": "Pending"})})  # no redirect url
        with patch("requests.post", side_effect=router), self.assertRaises(IotecPayError):
            initiate_card_collection(self.payment(method=Payment.Method.CARD))

    def test_disbursement_body_matches_spec(self):
        w = Withdrawal.objects.create(user=self.user, source=Withdrawal.Source.RIDER_EARNINGS, amount=10000, fee=500,
                                      net_amount=9500, phone="0701000000")
        router = post_router({"/api/disbursements/disburse": ok_json({"id": "d-1", "status": "Pending"})})
        with patch("requests.post", side_effect=router):
            initiate_disbursement(w)
        url, body = router.calls[-1]
        self.assertEqual(url, "https://pay.iotec.io/api/disbursements/disburse")
        self.assertEqual(body["category"], "MobileMoney")
        self.assertEqual(body["payee"], "256701000000")
        self.assertIsInstance(body["amount"], float)             # number, not a string
        self.assertEqual(body["amount"], 9500.0)
        w.refresh_from_db()
        self.assertEqual((w.status, w.provider_transaction_id), (Withdrawal.Status.PROCESSING, "d-1"))

    def test_disbursement_below_minimum_refused(self):
        w = Withdrawal.objects.create(user=self.user, source=Withdrawal.Source.RIDER_EARNINGS, amount=450, fee=0,
                                      net_amount=450, phone="0701000000")
        with patch("requests.post") as post, self.assertRaises(IotecPayError):
            initiate_disbursement(w)
        post.assert_not_called()

    def test_settings_expose_payment_providers_structure(self):
        from django.conf import settings
        cfg = settings.PAYMENT_PROVIDERS["IOTECH_PAY"]
        for key in ("PUBLIC_KEY", "SECRET_KEY", "BASE_URL", "WALLET_ID", "CURRENCY", "CALLBACK_URL"):
            self.assertIn(key, cfg)


class StatusTests(TestCase):
    def test_every_spec_status_is_classified(self):
        expect = {"Success": pstatus.SUCCESS, "Failed": pstatus.FAILED, "RolledBack": pstatus.FAILED,
                  "Cancelled": pstatus.FAILED, "Rejected": pstatus.FAILED, "SentToVendor": pstatus.SENT,
                  "Pending": pstatus.IN_PROGRESS, "AwaitingApproval": pstatus.IN_PROGRESS,
                  "Scheduled": pstatus.IN_PROGRESS}
        for raw, want in expect.items():
            self.assertEqual(pstatus.classify(raw), want, raw)
        self.assertEqual(pstatus.classify("SomethingNew"), pstatus.IN_PROGRESS)   # unknown never credits or fails
        self.assertEqual(pstatus.classify(None), pstatus.IN_PROGRESS)


@override_settings(**CFG)
class ReconcileAndVerifyTests(Base):
    def status_stub(self, body):
        return patch("payments.services.reconciliation.get_collection_status", return_value=body)

    def test_cancelled_rejected_rolledback_all_fail_the_payment(self):
        for st in ("Cancelled", "Rejected", "RolledBack", "Failed"):
            pay = self.payment(provider_transaction_id="tx", status=Payment.Status.PENDING)
            with self.status_stub({"status": st, "amount": 1000, "currency": "UGX"}):
                reconcile_payment(pay)
            pay.refresh_from_db()
            self.assertEqual(pay.status, Payment.Status.FAILED, st)

    def test_card_payment_stuck_in_sent_to_vendor_is_reconciled(self):
        pay = self.payment(method=Payment.Method.CARD, provider_transaction_id="tx", status=Payment.Status.SENT_TO_VENDOR)
        with self.status_stub({"status": "Success", "amount": 1000, "currency": "UGX"}):
            reconcile_payment(pay)
        pay.refresh_from_db()
        self.assertEqual(pay.status, Payment.Status.SUCCESS)

    def test_awaiting_approval_changes_nothing(self):
        pay = self.payment(provider_transaction_id="tx", status=Payment.Status.PENDING)
        with self.status_stub({"status": "AwaitingApproval"}):
            reconcile_payment(pay)
        pay.refresh_from_db()
        self.assertEqual(pay.status, Payment.Status.PENDING)

    def test_lost_initiation_response_falls_back_to_external_id(self):
        pay = self.payment(provider_transaction_id="", status=Payment.Status.PENDING)
        with patch("payments.services.reconciliation.get_collection_by_external_id",
                   return_value={"id": "found", "status": "Success", "amount": 1000, "currency": "UGX"}) as by_ext:
            reconcile_payment(pay)
        by_ext.assert_called_once_with(str(pay.internal_reference))
        pay.refresh_from_db()
        self.assertEqual(pay.status, Payment.Status.SUCCESS)

    def test_success_for_the_wrong_amount_is_flagged_not_credited(self):
        pay = self.payment(provider_transaction_id="tx", status=Payment.Status.PENDING)
        with self.status_stub({"status": "Success", "amount": 500, "currency": "UGX"}):
            reconcile_payment(pay)
        pay.refresh_from_db()
        self.assertEqual(pay.status, Payment.Status.REQUIRES_REVIEW)
        self.assertFalse(Payment.objects.filter(pk=pay.pk, status=Payment.Status.SUCCESS).exists())

    def test_wrong_currency_is_flagged(self):
        pay = self.payment(provider_transaction_id="tx", status=Payment.Status.PENDING)
        with self.status_stub({"status": "Success", "amount": 1000, "currency": "USD"}):
            reconcile_payment(pay)
        pay.refresh_from_db()
        self.assertEqual(pay.status, Payment.Status.REQUIRES_REVIEW)


@override_settings(**{**CFG, "DEBUG": False, "IOTEC_CALLBACK_SECRET": "shh-secret"})
class CallbackTests(Base):
    def post(self, payload, **headers):
        return self.client.post("/api/iotec/callback", json.dumps(payload), content_type="application/json", **headers)

    def test_single_url_works_with_and_without_trailing_slash(self):
        for path in ("/api/iotec/callback", "/api/iotec/callback/"):
            r = self.client.post(path, "{}", content_type="application/json", HTTP_X_CALLBACK_SECRET="shh-secret")
            self.assertEqual(r.status_code, 200, path)           # not a 301/302/500

    def test_secret_accepted_as_custom_header_or_bearer_and_rejected_otherwise(self):
        self.assertEqual(self.post({}, HTTP_X_CALLBACK_SECRET="shh-secret").status_code, 200)
        self.assertEqual(self.post({}, HTTP_AUTHORIZATION="Bearer shh-secret").status_code, 200)
        self.assertEqual(self.post({}, HTTP_X_CALLBACK_SECRET="wrong").status_code, 401)
        self.assertEqual(self.post({}, HTTP_AUTHORIZATION="Bearer wrong").status_code, 401)
        self.assertEqual(self.post({}).status_code, 401)

    @override_settings(IOTEC_CALLBACK_SECRET="")
    def test_no_secret_configured_fails_closed_outside_debug(self):
        self.assertEqual(self.post({}).status_code, 401)

    def test_collection_event_is_verified_with_ioTec_not_trusted(self):
        pay = self.payment(provider_transaction_id="tx", status=Payment.Status.PENDING)
        with patch("payments.services.reconciliation.get_collection_status", return_value={"status": "Pending"}):
            self.post({"externalId": str(pay.internal_reference), "status": "Success"}, HTTP_X_CALLBACK_SECRET="shh-secret")
        pay.refresh_from_db()
        self.assertEqual(pay.status, Payment.Status.PENDING)     # a forged "Success" credits nothing
        with patch("payments.services.reconciliation.get_collection_status",
                   return_value={"status": "Success", "amount": 1000, "currency": "UGX"}):
            self.post({"externalId": str(pay.internal_reference), "status": "Pending"}, HTTP_X_CALLBACK_SECRET="shh-secret")
        pay.refresh_from_db()
        self.assertEqual(pay.status, Payment.Status.SUCCESS)     # ioTec's answer wins

    def test_disbursement_event_is_routed_to_withdrawals(self):
        w = Withdrawal.objects.create(user=self.user, source=Withdrawal.Source.RIDER_EARNINGS, amount=10000, fee=0,
                                      net_amount=10000, phone="0701000000", provider_transaction_id="d-1",
                                      status=Withdrawal.Status.PROCESSING)
        with patch("payments.services.reconciliation.get_disbursement_status", return_value={"status": "Success"}):
            self.post({"externalId": str(w.internal_reference), "status": "Success"}, HTTP_X_CALLBACK_SECRET="shh-secret")
        w.refresh_from_db()
        self.assertEqual(w.status, Withdrawal.Status.COMPLETED)

    def test_garbage_payloads_never_crash_the_endpoint(self):
        for body in ({"externalId": "not-a-uuid"}, {"externalId": None}, {}, {"status": 5}):
            self.assertEqual(self.post(body, HTTP_X_CALLBACK_SECRET="shh-secret").status_code, 200, body)
        r = self.client.post("/api/iotec/callback", "[1,2", content_type="application/json", HTTP_X_CALLBACK_SECRET="shh-secret")
        self.assertIn(r.status_code, (200, 400))


@override_settings(**CFG)
class StatusEndpointAndReturnPageTests(Base):
    def test_status_endpoint_asks_ioTec_while_the_payment_is_open(self):
        pay = self.payment(provider_transaction_id="tx", status=Payment.Status.PENDING)
        self.client.force_login(self.user)
        with patch("payments.services.reconciliation.get_collection_status",
                   return_value={"status": "Success", "amount": 1000, "currency": "UGX"}) as st:
            r = self.client.get(reverse("payments:status", args=[pay.pk]))
        self.assertEqual(r.json()["data"]["status"], "success")
        st.assert_called_once()

    def test_status_endpoint_is_owner_only_and_throttled_per_payment(self):
        pay = self.payment(provider_transaction_id="tx", status=Payment.Status.PENDING)
        other = User.objects.create_user(phone="+256701999999", password="x", role=Role.MEMBER)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("payments:status", args=[pay.pk])).status_code, 404)
        self.client.force_login(self.user)
        with patch("payments.services.reconciliation.get_collection_status", return_value={"status": "Pending"}) as st:
            for _ in range(5):
                self.client.get(reverse("payments:status", args=[pay.pk]))
        self.assertEqual(st.call_count, 1)                       # polling can't hammer ioTec

    def test_return_page_is_owner_only_and_ignores_query_string_claims(self):
        pay = self.payment(method=Payment.Method.CARD, status=Payment.Status.SENT_TO_VENDOR)
        url = reverse("payment_return")
        self.assertEqual(self.client.get(f"{url}?ref={pay.internal_reference}").status_code, 302)   # login first
        self.client.force_login(self.user)
        r = self.client.get(f"{url}?ref={pay.internal_reference}&status=Success&id=whatever")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Checking payment status")
        pay.refresh_from_db()
        self.assertEqual(pay.status, Payment.Status.SENT_TO_VENDOR)  # "status=Success" in the URL changed nothing
        for bad in ("", "garbage", "00000000-0000-0000-0000-000000000000"):
            self.assertEqual(self.client.get(f"{url}?ref={bad}").status_code, 404, bad)
        other = User.objects.create_user(phone="+256701999998", password="x", role=Role.MEMBER)
        self.client.force_login(other)
        self.assertEqual(self.client.get(f"{url}?ref={pay.internal_reference}").status_code, 404)

    def test_card_payment_through_the_api_returns_the_hosted_page_url(self):
        self.client.force_login(self.user)
        router = post_router({"/api/collections/collect/card": ok_json(
            {"id": "tx-c", "status": "Pending", "cardRedirectUrl": "https://pay.iotec.io/pegpay/zzz"})})
        with patch("requests.post", side_effect=router):
            r = self.client.post(reverse("payments:initiate"), json.dumps({"purpose": "subscription", "method": "card"}),
                                 content_type="application/json")                # no email sent: account email is used
        self.assertEqual(r.status_code, 201, r.content)
        data = r.json()["data"]
        self.assertEqual(data["redirect_url"], "https://pay.iotec.io/pegpay/zzz")
        self.assertEqual(data["next_action"], "REDIRECT")
        self.assertEqual(router.calls[-1][1]["payer"], "amina@example.com")

    def test_member_page_offers_both_payment_methods(self):
        self.client.force_login(self.user)
        page = self.client.get(reverse("member"))
        self.assertContains(page, 'value="card"')
        self.assertContains(page, "data-method-switch")


@override_settings(**{**CFG, "IOTEC_CLIENT_ID": "PUBLIC-KEY-abc123", "IOTEC_CLIENT_SECRET": "very-private-value-987",
                      "IOTEC_WALLET_ID": "wallet-private-id-555",
                      "IOTECH_CALLBACK_URL": "https://shop.example.com/api/iotec/callback",
                      "IOTEC_CALLBACK_SECRET": "callback-private-value-321", "SITE_URL": "https://shop.example.com"})
class CheckCommandTests(TestCase):
    def run_cmd(self):
        out = StringIO()
        call_command("iotec_check", stdout=out)
        return out.getvalue()

    def test_reports_success_without_printing_secrets(self):
        with patch("payments.management.commands.iotec_check.get_access_token", return_value="tok"), \
             patch("payments.management.commands.iotec_check.get_wallet_balance",
                   return_value={"name": "Main", "currency": "UGX", "actualBalance": 125000}):
            text = self.run_cmd()
        self.assertIn("All checks passed", text)
        self.assertIn("125000", text)
        for private in ("PUBLIC-KEY-abc123", "very-private-value-987", "wallet-private-id-555", "callback-private-value-321"):
            self.assertNotIn(private, text)                      # credentials are never printed

    def test_reports_bad_credentials(self):
        from payments.services.iotec_auth import IotecAuthError
        with patch("payments.management.commands.iotec_check.get_access_token", side_effect=IotecAuthError("401")):
            self.assertIn("refused", self.run_cmd())

    @override_settings(IOTEC_WALLET_ID="")
    def test_reports_missing_values(self):
        self.assertIn("MISSING", self.run_cmd())


@override_settings(**CFG)
class AdminWalletTests(Base):
    def test_admin_payments_page_shows_wallet_balance_and_survives_outages(self):
        admin = User.objects.create_user(phone="+256701555555", password="x", role=Role.SUPER_ADMIN, is_superuser=True)
        self.client.force_login(admin)
        with patch("payments.services.iotec_disbursements.get_wallet_balance",
                   return_value={"name": "Main", "currency": "UGX", "actualBalance": 98000}):
            self.assertContains(self.client.get(reverse("admin_payments")), "98,000")
        cache.clear()
        with patch("payments.services.iotec_disbursements.get_wallet_balance", side_effect=IotecPayError("down")):
            self.assertContains(self.client.get(reverse("admin_payments")), "Couldn't reach ioTec")
