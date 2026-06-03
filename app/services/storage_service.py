import io
import uuid
import logging

from fastapi import HTTPException, UploadFile
from PIL import Image

from app.database import get_supabase

logger = logging.getLogger(__name__)

_ALLOWED_TYPES = {"image/jpeg", "image/png", "application/pdf"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB

# Manual magic-byte signatures — (expected_bytes, prefix_length)
_MAGIC: dict[str, tuple[bytes, int]] = {
    "image/jpeg":      (b"\xff\xd8\xff",           3),
    "image/png":       (b"\x89PNG\r\n\x1a\n",      8),
    "application/pdf": (b"\x25\x50\x44\x46",       4),  # %PDF
}

_EXT: dict[str, str] = {
    "image/jpeg":      "jpg",
    "image/png":       "png",
    "application/pdf": "pdf",
}


def _check_magic(content: bytes, content_type: str) -> bool:
    entry = _MAGIC.get(content_type)
    if entry is None:
        return False
    signature, length = entry
    return content[:length] == signature


def _strip_metadata(content: bytes, content_type: str) -> bytes:
    """Re-encode image through Pillow into a fresh buffer, stripping all EXIF/metadata."""
    buf = io.BytesIO()
    img = Image.open(io.BytesIO(content))
    if content_type == "image/jpeg":
        img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=90)
    else:  # PNG — preserve transparency but drop metadata chunks
        img.save(buf, format="PNG")
    return buf.getvalue()


async def upload_image(image: UploadFile) -> str:
    """Validate, sanitize, and upload a file.  Returns the public URL.
    Accepts: image/jpeg, image/png, application/pdf.  Max 5 MB."""
    content_type = (image.content_type or "").lower()

    if content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Μη επιτρεπτός τύπος αρχείου. Επιτρέπονται: JPEG, PNG, PDF.",
        )

    file_bytes = await image.read()

    if len(file_bytes) > _MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail="Το αρχείο υπερβαίνει το μέγιστο μέγεθος των 5 MB.",
        )

    if not _check_magic(file_bytes, content_type):
        raise HTTPException(
            status_code=400,
            detail="Μη έγκυρο αρχείο: η υπογραφή δεν αντιστοιχεί στον δηλωμένο τύπο.",
        )

    # Strip EXIF / embedded metadata from images; PDFs pass through unchanged
    if content_type in ("image/jpeg", "image/png"):
        try:
            file_bytes = _strip_metadata(file_bytes, content_type)
        except Exception as e:
            logger.error(f"[UPLOAD] Metadata strip failed: {e}")
            raise HTTPException(status_code=400, detail="Μη έγκυρο αρχείο εικόνας.")

    ext = _EXT[content_type]
    file_name = f"{uuid.uuid4()}.{ext}"

    logger.info(f"[UPLOAD] {file_name} {len(file_bytes)}B {content_type}")

    client = get_supabase()
    client.storage.from_("report-images").upload(
        path=file_name,
        file=file_bytes,
        file_options={"content-type": content_type},
    )

    url = client.storage.from_("report-images").get_public_url(file_name)
    logger.info(f"[UPLOAD] OK: {file_name}")
    return url
