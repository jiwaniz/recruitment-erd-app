"""Send email through SMTP. Configure [email] in Streamlit secrets or EMAIL_* variables (see AUTH_SETUP.md)."""
import smtplib
import ssl
from email.message import EmailMessage

from .config import get_email_config


def is_configured() -> bool:
    c = get_email_config()
    return bool(c["host"] and c["from_address"])


def send(to: str, subject: str, body: str) -> None:
    c = get_email_config()
    if not (c["host"] and c["from_address"]):
        raise RuntimeError("Email service is not configured.")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = c["from_address"], to, subject
    msg.set_content(body)
    if c["security"] == "ssl":
        server = smtplib.SMTP_SSL(c["host"], c["port"], timeout=15, context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(c["host"], c["port"], timeout=15)
    with server:
        if c["security"] == "starttls":
            server.starttls(context=ssl.create_default_context())
        if c["username"]:
            server.login(c["username"], c["password"] or "")
        server.send_message(msg)
