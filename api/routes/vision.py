import os
import base64
import httpx
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from PIL import Image
import io
from api.dependencies import get_current_user
from core.config import VISION_PROVIDER
import pytesseract

from db.models import User
from services.media_ocr import save_image  # pip install pytesseract pillow
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
import logging

router = APIRouter(prefix="/image_upload", tags=["vision"])
log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def pil_to_b64(image: Image.Image, fmt: str = "JPEG") -> str:
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode()

# ------------------------------------------------------------------
# 1.  FREE / CPU  –  Tesseract
# ------------------------------------------------------------------
def extract_text_from_image_tesseract(b64_image: str) -> str:
    """
    Uses Tesseract OCR.  No GPU, no API key, completely local.
    """
    try:
        raw = base64.b64decode(b64_image)
        image = Image.open(io.BytesIO(raw))
        text = pytesseract.image_to_string(image, lang="eng").strip()
        return text
    except Exception as e:
        log.exception("Tesseract OCR failed")
        raise RuntimeError("OCR failed") from e

# ------------------------------------------------------------------
# 2.  OPENAI GPT-4o  (kept untouched)
# ------------------------------------------------------------------
def extract_text_from_image_openai(b64_image: str) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o",
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Return only the text you see, no chatter."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
                    },
                ],
            }
        ],
    }

    r = httpx.post(url, headers=headers, json=payload, timeout=30)
    if r.status_code != 200:
        raise RuntimeError("LLM vision call failed")
    return r.json()["choices"][0]["message"]["content"].strip()

# ------------------------------------------------------------------
# Router
# ------------------------------------------------------------------
@router.post("/parse")
async def parse_image(file: UploadFile = File(...)):
    try:
        image = Image.open(file.file).convert("RGB")
    except Exception:
        raise HTTPException(400, "Invalid image")

    b64 = pil_to_b64(image)

    provider = VISION_PROVIDER  # cpu | openai
    if provider == "openai":
        text = extract_text_from_image_openai(b64)
    else:
        text = extract_text_from_image_tesseract(b64)

    return {"text": text}



# ------------------------------------------------------------------
# Upload Image
# ------------------------------------------------------------------
@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    if not file.content_type.startswith("image/"):
        raise HTTPException(400, "Invalid image")

    url = await save_image(file)
    return {"url": url}
