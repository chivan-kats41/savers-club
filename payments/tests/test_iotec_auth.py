from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from payments.services.iotec_auth import IotecAuthError, TOKEN_CACHE_KEY, get_access_token


@override_settings(IOTEC_CLIENT_ID="test-id", IOTEC_CLIENT_SECRET="test-secret", IOTEC_TOKEN_URL="https://id.iotec.io/connect/token")
class IotecAuthTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("payments.services.iotec_auth.requests.post")
    def test_fetches_and_caches_token(self, mock_post):
        mock_post.return_value = Mock(status_code=200, json=lambda: {"access_token": "abc123", "expires_in": 300})
        token = get_access_token()
        self.assertEqual(token, "abc123")
        self.assertEqual(mock_post.call_count, 1)

        # Second call should hit the cache, not the network.
        token2 = get_access_token()
        self.assertEqual(token2, "abc123")
        self.assertEqual(mock_post.call_count, 1)

    @patch("payments.services.iotec_auth.requests.post")
    def test_never_sends_or_logs_secret_in_a_gettable_way(self, mock_post):
        mock_post.return_value = Mock(status_code=200, json=lambda: {"access_token": "abc123", "expires_in": 300})
        get_access_token()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["data"]["client_secret"], "test-secret")  # sent to ioTec, correctly
        self.assertNotIn("client_secret", cache.get(TOKEN_CACHE_KEY, ""))  # never cached alongside the token

    @patch("payments.services.iotec_auth.requests.post")
    def test_auth_failure_raises(self, mock_post):
        mock_post.return_value = Mock(status_code=401, json=lambda: {"error": "invalid_client"})
        with self.assertRaises(IotecAuthError):
            get_access_token()

    @override_settings(IOTEC_CLIENT_ID="", IOTEC_CLIENT_SECRET="")
    def test_missing_credentials_raises_without_network_call(self):
        with self.assertRaises(IotecAuthError):
            get_access_token()
