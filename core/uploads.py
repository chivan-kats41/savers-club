"""Safe handling of user uploads.

Never trust the file name, extension or Content-Type from the client. Images
are decoded with Pillow and re-encoded (which drops EXIF/GPS data and any
polyglot payload); PDFs must start with the %PDF- magic bytes. Sizes and pixel
counts are capped before decoding to avoid decompression bombs.
"""
import io
import secrets

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from PIL import Image, UnidentifiedImageError

MAX_PIXELS = 25_000_000
MAX_SIDE = 1600


def private_storage():
    """Storage outside MEDIA_ROOT: never exposed by the web server directly."""
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT, base_url=None)


def clean_image(upload, max_bytes=5 * 1024 * 1024) -> ContentFile:
    if upload.size > max_bytes:
        raise ValidationError(f"Image must be {max_bytes // (1024 * 1024)}MB or smaller.")
    try:
        img = Image.open(upload)
        if img.width * img.height > MAX_PIXELS:
            raise ValidationError("Image dimensions are too large.")
        if img.format not in ("JPEG", "PNG", "WEBP"):
            raise ValidationError("Only JPEG, PNG or WebP images are allowed.")
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValidationError("That file isn't a valid image.")
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85, optimize=True)  # fresh pixels only: no EXIF, no trailing data
    return ContentFile(out.getvalue(), name=f"{secrets.token_hex(12)}.jpg")


def clean_document(upload, max_bytes=8 * 1024 * 1024) -> ContentFile:
    """ID documents: image (re-encoded) or PDF (magic-byte check)."""
    if upload.size > max_bytes:
        raise ValidationError(f"File must be {max_bytes // (1024 * 1024)}MB or smaller.")
    head = upload.read(5)
    upload.seek(0)
    if head == b"%PDF-":
        return ContentFile(upload.read(), name=f"{secrets.token_hex(12)}.pdf")
    return clean_image(upload, max_bytes=max_bytes)
