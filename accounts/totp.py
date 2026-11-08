"""RFC 6238 TOTP (SHA-1, 6 digits, 30s) using only the standard library."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def matching_step(secret: str, code: str, window: int = 1, now: float | None = None) -> int | None:
    """The 30-second step `code` is valid for (current step ±`window` for clock drift), or None."""
    code = (code or "").strip().replace(" ", "")
    if not secret or len(code) != 6 or not code.isdigit():
        return None
    step = int((now if now is not None else time.time()) // 30)
    for d in range(-window, window + 1):
        if hmac.compare_digest(_code(secret, step + d), code):
            return step + d
    return None


def verify(secret: str, code: str, window: int = 1, now: float | None = None) -> bool:
    return matching_step(secret, code, window, now) is not None


# ---- encryption at rest -----------------------------------------------------------------------------------------
# A database leak must not hand out working second factors, so secrets are stored encrypted (Fernet). The key comes
# from TOTP_ENCRYPTION_KEY, else is derived from SECRET_KEY. Values written before encryption existed (no prefix)
# are still readable and get encrypted by migration accounts.0004.
_PREFIX = "enc1:"


def _fernet():
    from cryptography.fernet import Fernet
    from django.conf import settings

    seed = getattr(settings, "TOTP_ENCRYPTION_KEY", "") or settings.SECRET_KEY
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(seed.encode()).digest()))


def encrypt_secret(raw: str) -> str:
    if not raw:
        return ""
    return _PREFIX + _fernet().encrypt(raw.encode()).decode()


def decrypt_secret(stored: str) -> str:
    if not stored:
        return ""
    if not stored.startswith(_PREFIX):
        return stored  # legacy plaintext
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(stored[len(_PREFIX):].encode()).decode()
    except InvalidToken:
        return ""  # wrong key: treated as "no usable secret", never a crash


def provisioning_uri(secret: str, account: str, issuer: str = "1K Saver Club") -> str:
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}&digits=6&period=30"
