from faster_whisper import WhisperModel
from threading import Lock

_model = None
_lock = Lock()

def get_whisper_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = WhisperModel(
                    "base",
                    device="cpu",
                    compute_type="int8"
                )
    return _model
