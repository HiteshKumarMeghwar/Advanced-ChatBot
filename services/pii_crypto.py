import re
from cryptography.fernet import Fernet, InvalidToken
from core.config import FERNET_KEY

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PHONE_RE = re.compile(r"\b(\+?\d{1,3}[\s-]?)?\d{7,15}\b")

# 🔁 Key ring support (comma-separated keys)
_KEYS = [k.strip().encode() for k in FERNET_KEY.split(",")]
_FERNETS = [Fernet(k) for k in _KEYS]

def detect_pii_type(text: str) -> str | None:
    if EMAIL_RE.search(text):
        return "email"
    if PHONE_RE.search(text):
        return "phone"
    return None

def encrypt_fact(text: str) -> str:
    # Always encrypt with newest key
    return _FERNETS[0].encrypt(text.encode()).decode()

def decrypt_fact(ciphertext: str) -> str:
    for f in _FERNETS:
        try:
            return f.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            continue
    raise InvalidToken("No valid Fernet key found")
