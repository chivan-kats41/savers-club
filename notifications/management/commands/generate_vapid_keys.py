"""Print a fresh VAPID key pair for Web Push. Run once; put the values in .env and keep the private key secret.

    python manage.py generate_vapid_keys
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class Command(BaseCommand):
    help = "Generate a VAPID public/private key pair for Web Push notifications."

    def handle(self, *args, **options):
        key = ec.generate_private_key(ec.SECP256R1())
        private = _b64(key.private_numbers().private_value.to_bytes(32, "big"))
        public = _b64(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
        self.stdout.write("Add these to your .env (the private key is a SECRET: never commit or share it):\n")
        self.stdout.write(f"VAPID_PUBLIC_KEY={public}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={private}")
        self.stdout.write("VAPID_CONTACT=mailto:you@yourdomain.com   # a real contact address; push services may use it to reach you")
