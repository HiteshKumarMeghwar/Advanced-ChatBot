import uuid
from pathlib import Path
from fastapi import UploadFile
from core.config import INTERNAL_BASE_URL

BASE_DIR = Path(__file__).resolve().parent.parent
IMAGE_DIR = BASE_DIR / "images_ocr"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

async def save_image(file: UploadFile) -> str:
    ext = Path(file.filename).suffix.lower()
    filename = f"{uuid.uuid4()}{ext}"
    path = IMAGE_DIR / filename

    with open(path, "wb") as f:
        f.write(await file.read())

    # URL exposed via static mount
    return f"{INTERNAL_BASE_URL}/media_ocr/images/{filename}"
