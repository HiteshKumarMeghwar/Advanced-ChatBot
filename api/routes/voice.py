from fastapi import APIRouter, UploadFile, File, HTTPException
import tempfile
import os
from core.config import BEAM_SIZE, VAD_FILTER, VAD_PARAMETERS
from services.whisper_service import get_whisper_model

router = APIRouter(prefix="/voice", tags=["voice"])


# -----------------------------
# Transcribe endpoint
# -----------------------------
@router.post("/transcribe")
async def transcribe_voice(file: UploadFile = File(...)):
    model = get_whisper_model()
    if not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Invalid audio file")

    # Save temp file (safe + fast)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        segments, info = model.transcribe(
            tmp_path,
            beam_size=BEAM_SIZE,
            vad_filter=VAD_FILTER,
            vad_parameters={
                "min_silence_duration_ms": VAD_PARAMETERS,
            },
        )

        text = " ".join(seg.text for seg in segments).strip()

        if not text:
            raise HTTPException(status_code=422, detail="No speech detected")

        return {
            "text": text,
            "language": info.language,
            "confidence": info.language_probability,
        }

    finally:
        os.unlink(tmp_path)
