# services/mail.py
import anyio
from core.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS
from aiosmtplib import send
from email.message import EmailMessage

async def send_email(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    await send(msg, hostname=SMTP_HOST, port=SMTP_PORT, username=SMTP_USER, password=SMTP_PASS)