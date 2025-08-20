import os
import smtplib
from email.message import EmailMessage
from typing import Optional

import requests


INTERNAL_WEBHOOK_URL = os.getenv("INTERNAL_WEBHOOK_URL")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")  # Comma-separated


def send_internal_notification(subject: str, content: str) -> None:
    delivered = False
    # Try webhook first
    if INTERNAL_WEBHOOK_URL:
        try:
            resp = requests.post(INTERNAL_WEBHOOK_URL, json={"subject": subject, "content": content}, timeout=10)
            resp.raise_for_status()
            delivered = True
        except Exception:
            delivered = False

    if delivered:
        return

    # fallback to email if configured
    if SMTP_HOST and SMTP_USER and SMTP_PASS and EMAIL_FROM and EMAIL_TO:
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = EMAIL_FROM
            msg["To"] = EMAIL_TO
            msg.set_content(content)

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
            delivered = True
        except Exception:
            delivered = False

    if not delivered:
        # As last resort, print to stdout (logs)
        print(f"[NOTIFICATION] {subject}\n{content}")


def notify_error(subject: str, content: str) -> None:
    try:
        send_internal_notification(subject, content)
    except Exception:
        pass


