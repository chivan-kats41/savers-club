import logging

import requests
from django.conf import settings

from .iotec_auth import IotecAuthError, get_access_token

logger = logging.getLogger("payments")


class IotecPayError(Exception):
    """Raised for any non-2xx ioTec response or transport failure. The
    message is safe to surface to the caller (never includes secrets);
    full details are logged server-side only.

    Plain IotecPayError means ioTec DEFINITELY did not act on the request
    (rejected, bad credentials, validation). Callers may safely release
    whatever they reserved. See IotecUncertainError for the other case."""


class IotecUncertainError(IotecPayError):
    """The request may have been processed but we never saw the answer (timeout, dropped
    connection, 5xx). Money may have moved. Callers must NOT discard their local record or
    release reserved funds: keep it pending and let reconciliation ask ioTec by externalId."""


class IotecNotFound(IotecPayError):
    """ioTec answered 404 for a status lookup: it has no record of that id."""


def _sanitized(payload: dict) -> dict:
    """Never let secrets end up in logs, even by accident."""
    redacted = dict(payload or {})
    for key in ("client_secret", "walletId", "access_token"):
        if key in redacted:
            redacted[key] = "***"
    return redacted


class IotecPayClient:
    def __init__(self):
        self.base_url = settings.IOTEC_BASE_URL.rstrip("/")

    def _headers(self):
        try:
            token = get_access_token()
        except IotecAuthError as exc:
            raise IotecPayError(str(exc)) from exc
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def post(self, path: str, json_body: dict, timeout: int = 15) -> dict:
        url = f"{self.base_url}{path}"
        headers = self._headers()
        try:
            resp = requests.post(url, json=json_body, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            logger.error("ioTec POST %s network error: %s", path, exc)
            # A POST that timed out may still have been executed by ioTec.
            raise IotecUncertainError("Could not confirm the request with ioTec Pay.") from exc
        return self._handle_response(path, resp)

    def get(self, path: str, timeout: int = 15) -> dict:
        url = f"{self.base_url}{path}"
        headers = self._headers()
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            logger.error("ioTec GET %s network error: %s", path, exc)
            raise IotecPayError("Could not reach ioTec Pay.") from exc
        return self._handle_response(path, resp)

    def _handle_response(self, path: str, resp: requests.Response) -> dict:
        try:
            data = resp.json()
        except ValueError:
            data = {}

        if resp.status_code >= 400:
            logger.error("ioTec %s returned status=%s body=%s", path, resp.status_code, _sanitized(data))
            if resp.status_code in (401, 403):
                # token may have been revoked/rotated: drop the cached one so the next call re-authenticates
                from django.core.cache import cache
                from .iotec_auth import TOKEN_CACHE_KEY
                cache.delete(TOKEN_CACHE_KEY)
                raise IotecPayError("ioTec rejected our credentials. Check IOTEC_API_KEY / IOTEC_SECRET_KEY.")
            if resp.status_code == 404:
                raise IotecNotFound("ioTec has no record of that transaction.")
            message = data.get("message") or data.get("error") or f"ioTec API error (status {resp.status_code})"
            if resp.status_code >= 500:
                raise IotecUncertainError(message)
            raise IotecPayError(message)

        return data
