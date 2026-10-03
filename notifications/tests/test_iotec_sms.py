"""ioTec Messaging gateway: request shape (per the OpenAPI spec), failure handling, OTP delivery."""
import logging
import uuid
from unittest import mock

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from notifications.services import sms_gateway as g
from notifications.services.sms_gateway import IoTecSMSGateway, SMSTemporaryError, send_sms, to_iotec_number

CREDS = dict(
    SMS_GATEWAY_CLASS="notifications.services.sms_gateway.IoTecSMSGateway",
    IOTEC_MESSAGING_CLIENT_ID="client-123",
    IOTEC_MESSAGING_API_KEY="super-secret-key",
    IOTEC_MESSAGING_BASE_URL="https://messaging-api.iotec.io",
    IOTEC_MESSAGING_PHONE_FORMAT="local",
)


def fake_response(status=200, json_body=None):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = json_body if json_body is not None else {"id": str(uuid.uuid4()), "status": "Pending"}
    return r


@override_settings(**CREDS)
class GatewayTests(TestCase):
    def test_request_matches_the_api_spec(self):
        with mock.patch("requests.post", return_value=fake_response()) as post:
            self.assertTrue(IoTecSMSGateway().send("+256712345678", "Hello there"))
        (url,), kw = post.call_args
        self.assertEqual(url, "https://messaging-api.iotec.io/api/sms-message")
        self.assertEqual(kw["headers"]["Client-Id"], "client-123")
        self.assertEqual(kw["headers"]["X-Api-Key"], "super-secret-key")
        self.assertEqual(kw["json"]["recipient"], "0712345678")      # local format, as in the docs
        self.assertEqual(kw["json"]["body"], "Hello there")
        self.assertTrue(kw["json"]["referenceId"].startswith("1k-"))
        self.assertEqual(kw["timeout"], 10)

    def test_phone_format_options_and_validation(self):
        cases = {"+256712345678": "0712345678", "256712345678": "0712345678", "0712345678": "0712345678",
                 "712345678": "0712345678", "+256 712-345 678": "0712345678"}
        for raw, want in cases.items():
            self.assertEqual(to_iotec_number(raw), want, raw)
        with override_settings(IOTEC_MESSAGING_PHONE_FORMAT="international"):
            self.assertEqual(to_iotec_number("0712345678"), "256712345678")
        with override_settings(IOTEC_MESSAGING_PHONE_FORMAT="plus"):
            self.assertEqual(to_iotec_number("0712345678"), "+256712345678")
        for bad in ("", "abc", "12345", "+254712345678", "0212345678", "0712345678; DROP", "+2567123456789"):
            self.assertIsNone(to_iotec_number(bad), bad)

    def test_invalid_number_is_never_sent(self):
        with mock.patch("requests.post") as post:
            self.assertFalse(IoTecSMSGateway().send("not-a-number", "hi"))
        post.assert_not_called()

    def test_failed_status_returns_false(self):
        body = {"id": str(uuid.uuid4()), "status": "Failed", "errorMessage": "Insufficient balance"}
        with mock.patch("requests.post", return_value=fake_response(200, body)):
            self.assertFalse(IoTecSMSGateway().send("0712345678", "hi"))

    def test_bad_credentials_do_not_retry_and_dont_leak_key(self):
        with mock.patch("requests.post", return_value=fake_response(401, {})), self.assertLogs("notifications", "ERROR") as logs:
            self.assertFalse(IoTecSMSGateway().send("0712345678", "hi"))
        self.assertNotIn("super-secret-key", "\n".join(logs.output))

    def test_temporary_failures_raise_for_retry(self):
        for effect in (requests.Timeout(), requests.ConnectionError()):
            with mock.patch("requests.post", side_effect=effect):
                with self.assertRaises(SMSTemporaryError):
                    IoTecSMSGateway().send("0712345678", "hi")
        for code in (429, 500, 503):
            with mock.patch("requests.post", return_value=fake_response(code, {})):
                with self.assertRaises(SMSTemporaryError):
                    IoTecSMSGateway().send("0712345678", "hi")

    def test_send_sms_wrapper_swallows_by_default_but_can_raise(self):
        with mock.patch("requests.post", side_effect=requests.Timeout()):
            self.assertFalse(send_sms("0712345678", "hi"))
            with self.assertRaises(SMSTemporaryError):
                send_sms("0712345678", "hi", raise_transient=True)

    def test_long_messages_are_capped_and_empty_not_sent(self):
        with mock.patch("requests.post", return_value=fake_response()) as post:
            IoTecSMSGateway().send("0712345678", "x" * 2000)
            self.assertEqual(len(post.call_args.kwargs["json"]["body"]), g.MAX_BODY_CHARS)
            post.reset_mock()
            self.assertFalse(IoTecSMSGateway().send("0712345678", "   "))
            post.assert_not_called()

    def test_message_body_and_full_number_are_not_logged(self):
        with mock.patch("requests.post", return_value=fake_response()), self.assertLogs("notifications", "INFO") as logs:
            IoTecSMSGateway().send("0712345678", "Your code is 482913")
        out = "\n".join(logs.output)
        self.assertNotIn("482913", out)
        self.assertNotIn("0712345678", out)

    @override_settings(IOTEC_MESSAGING_CLIENT_ID="", IOTEC_MESSAGING_API_KEY="")
    def test_missing_credentials_fail_safely(self):
        with mock.patch("requests.post") as post:
            self.assertFalse(IoTecSMSGateway().send("0712345678", "hi"))
        post.assert_not_called()

    def test_status_lookup_hits_the_documented_endpoint(self):
        rid = str(uuid.uuid4())
        resp = fake_response(200, {"id": rid, "status": "Sent"})
        resp.raise_for_status = mock.Mock()
        with mock.patch("requests.get", return_value=resp) as get:
            self.assertEqual(g.get_sms_status(rid)["status"], "Sent")
        self.assertEqual(get.call_args.args[0], f"https://messaging-api.iotec.io/api/sms-message/{rid}")
        with self.assertRaises(ValueError):
            g.get_sms_status("../../etc/passwd")                    # request id must be a UUID


@override_settings(**CREDS)
class CommandAndCheckTests(TestCase):
    def test_sms_test_command(self):
        with mock.patch("requests.post", return_value=fake_response()):
            call_command("sms_test", "+256712345678", verbosity=0)
        with mock.patch("requests.post", return_value=fake_response(200, {"status": "Failed"})):
            with self.assertRaises(CommandError):
                call_command("sms_test", "+256712345678", verbosity=0)

    @override_settings(IOTEC_MESSAGING_CLIENT_ID="")
    def test_deploy_check_warns_on_missing_credentials(self):
        from notifications.checks import sms_configured
        self.assertEqual(sms_configured(None)[0].id, "notifications.W002")

    @override_settings(SMS_GATEWAY_CLASS="notifications.services.sms_gateway.ConsoleSMSGateway")
    def test_deploy_check_warns_on_console_gateway(self):
        from notifications.checks import sms_configured
        self.assertEqual(sms_configured(None)[0].id, "notifications.W001")


@override_settings(**CREDS)
class OtpDeliveryTests(TestCase):
    def test_registration_sends_the_otp_by_sms_and_never_exposes_it_outside_debug(self):
        from django.core.cache import cache
        from core.models import Area
        cache.clear()
        area = Area.objects.create(name="Testville")
        with override_settings(DEBUG=False), mock.patch("requests.post", return_value=fake_response()) as post:
            r = self.client.post(reverse("accounts:register"), {
                "phone": "+256700555111", "email": "n@example.com", "first_name": "N", "last_name": "U", "area": area.id,
                "password": "Str0ng-Pass-123!", "password_confirm": "Str0ng-Pass-123!",
            }, follow=True)
        self.assertTrue(post.called, "registration must send the OTP by SMS")
        bodies = [c.kwargs["json"] for c in post.call_args_list]
        otp_msgs = [b for b in bodies if "expires in 10 minutes" in b["body"]]
        self.assertEqual(len(otp_msgs), 1, bodies)             # (the other SMS is the welcome notification)
        sent = otp_msgs[0]
        self.assertEqual(sent["recipient"], "0700555111")
        self.assertRegex(sent["body"], r"\b\d{4}\b")
        code = __import__("re").search(r"\b(\d{4})\b", sent["body"]).group(1)
        self.assertNotContains(r, code)                      # the code must not appear in the page outside DEBUG

    def test_retry_task_retries_only_on_temporary_errors(self):
        from notifications.tasks import send_sms_notification
        with mock.patch("notifications.tasks.send_sms", return_value=False) as s:
            self.assertFalse(send_sms_notification.apply(args=("0712345678", "hi")).get())   # permanent failure: no retry
            self.assertEqual(s.call_count, 1)
        with mock.patch("notifications.tasks.send_sms", side_effect=SMSTemporaryError("down")) as s:
            from celery.exceptions import Retry
            with self.assertRaises(Retry):                    # a retry was scheduled (eager mode surfaces it instead of waiting)
                send_sms_notification.apply(args=("0712345678", "hi"))
            self.assertEqual(s.call_count, 1)

    def test_otp_helper_sends_sms_and_gates_code_on_debug(self):
        from accounts.views import _send_otp_dev
        user = User.objects.create_user(phone="+256700555222", password="x")
        with override_settings(DEBUG=False), mock.patch("requests.post", return_value=fake_response()) as post:
            self.assertIsNone(_send_otp_dev(user, "123456", "password-reset"))
        self.assertIn("123456", post.call_args.kwargs["json"]["body"])
        self.assertIn("reset your password", post.call_args.kwargs["json"]["body"])
        with override_settings(DEBUG=True), mock.patch("requests.post", return_value=fake_response()):
            self.assertEqual(_send_otp_dev(user, "654321", "registration"), "654321")

    def test_otp_helper_survives_provider_outage(self):
        from accounts.views import _send_otp_dev
        user = User.objects.create_user(phone="+256700555333", password="x")
        with override_settings(DEBUG=False), mock.patch("requests.post", side_effect=requests.Timeout()):
            self.assertIsNone(_send_otp_dev(user, "111222", "registration"))   # no exception, user can resend

    def test_otp_is_not_written_to_server_logs(self):
        from accounts.views import _send_otp_dev
        user = User.objects.create_user(phone="+256700555444", password="x")
        with mock.patch("requests.post", return_value=fake_response()), self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger("notifications").info("marker")
            _send_otp_dev(user, "909090", "registration")
        self.assertNotIn("909090", "\n".join(logs.output))
