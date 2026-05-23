from fastapi import UploadFile
from app.database import supabase
import uuid

async def upload_image(image: UploadFile) -> str:
    try:
        file_bytes = await image.read()
        file_ext = image.filename.split(".")[-1] if image.filename else "jpg"
        file_name = f"{uuid.uuid4()}.{file_ext}"

        print(f"📸 Uploading: {file_name} ({len(file_bytes)} bytes)")

        supabase.storage.from_("report-images").upload(
            path=file_name,
            file=file_bytes,
            file_options={"content-type": image.content_type or "image/jpeg"}
        )

        url = supabase.storage.from_("report-images").get_public_url(file_name)
        print(f"✅ Upload OK: {url}")
        return url

    except Exception as e:
        print(f"❌ Upload error: {str(e)}")
        raise