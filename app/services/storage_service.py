import uuid
import logging

from fastapi import HTTPException, UploadFile

from app.database import get_supabase

logger = logging.getLogger(__name__)

_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


def _check_magic_bytes(content: bytes, content_type: str) -> bool:
    if content_type == "image/jpeg":
        return content[:3] == b"\xff\xd8\xff"
    if content_type == "image/png":
        return content[:8] == b"\x89PNG\r\n\x1a\n"
    if content_type == "image/webp":
        return content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False


async def upload_image(image: UploadFile) -> str:
    content_type = (image.content_type or "").lower()
    if content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Μη επιτρεπτός τύπος αρχείου. Επιτρέπονται: JPEG, PNG, WebP.",
        )

    file_bytes = await image.read()

    if len(file_bytes) > _MAX_BYTES:
        raise HTTPException(status_code=400, detail="Το αρχείο υπερβαίνει το μέγιστο μέγεθος των 5 MB.")

    if not _check_magic_bytes(file_bytes, content_type):
        raise HTTPException(status_code=400, detail="Μη έγκυρο αρχείο εικόνας.")

    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
    file_name = f"{uuid.uuid4()}.{ext_map[content_type]}"

    logger.info(f"Uploading image: {file_name} ({len(file_bytes)} bytes, {content_type})")

    client = get_supabase()
    client.storage.from_("report-images").upload(
        path=file_name,
        file=file_bytes,
        file_options={"content-type": content_type},
    )

    url = client.storage.from_("report-images").get_public_url(file_name)
    logger.info(f"Image upload OK: {file_name}")
    return url
