import os
import logging
import requests
from typing import List, Optional


logger = logging.getLogger(__name__)

EVOLUTION_BASE_URL = os.getenv("EVOLUTION_API_BASE_URL", "")
EVOLUTION_INSTANCE_ID = os.getenv("EVOLUTION_INSTANCE_ID", "")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
PUBLIC_WEBHOOK_URL = os.getenv("PUBLIC_WEBHOOK_URL", "")


def _endpoint_send_text() -> str:
    # Common Evolution endpoint pattern
    base = EVOLUTION_BASE_URL.rstrip("/")
    return f"{base}/message/sendText/{EVOLUTION_INSTANCE_ID}"


def _endpoint_send_media() -> str:
    base = EVOLUTION_BASE_URL.rstrip("/")
    return f"{base}/message/sendMedia/{EVOLUTION_INSTANCE_ID}"


def _endpoint_set_webhook() -> str:
    base = EVOLUTION_BASE_URL.rstrip("/")
    return f"{base}/webhook/set/{EVOLUTION_INSTANCE_ID}"


def send_whatsapp_message(number: str, text: str) -> None:
    if not (EVOLUTION_BASE_URL and EVOLUTION_INSTANCE_ID and EVOLUTION_API_KEY):
        raise RuntimeError("Evolution API não configurada. Defina EVOLUTION_API_BASE_URL, EVOLUTION_INSTANCE_ID, EVOLUTION_API_KEY.")

    payload = {
        "number": number,
        "text": text,
    }
    headers = {
        "Content-Type": "application/json",
        "apikey": EVOLUTION_API_KEY,
    }
    url = _endpoint_send_text()
    logger.info("whatsapp.send_text", extra={"number": number, "len": len(text)})
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()


def send_whatsapp_media(number: str, caption: Optional[str], media_url: Optional[str] = None,
                        media_base64: Optional[str] = None, filename: Optional[str] = None) -> None:
    if not (EVOLUTION_BASE_URL and EVOLUTION_INSTANCE_ID and EVOLUTION_API_KEY):
        raise RuntimeError("Evolution API não configurada. Defina EVOLUTION_API_BASE_URL, EVOLUTION_INSTANCE_ID, EVOLUTION_API_KEY.")
    if not media_url and not media_base64:
        raise ValueError("Forneça media_url ou media_base64")

    payload = {
        "number": number,
        "caption": caption or "",
    }
    if media_url:
        payload["mediaUrl"] = media_url
    if media_base64:
        payload["mediaBase64"] = media_base64
    if filename:
        payload["fileName"] = filename

    headers = {
        "Content-Type": "application/json",
        "apikey": EVOLUTION_API_KEY,
    }
    url = _endpoint_send_media()
    logger.info("whatsapp.send_media", extra={"number": number, "has_url": bool(media_url), "has_base64": bool(media_base64)})
    resp = requests.post(url, json=payload, headers=headers, timeout=20)
    resp.raise_for_status()


def ensure_webhook(url_override: Optional[str] = None, events: Optional[List[str]] = None,
                   webhook_by_events: bool = True, webhook_base64: bool = False) -> None:
    """Configura o webhook da instância via API, se PUBLIC_WEBHOOK_URL estiver definido."""
    if not (EVOLUTION_BASE_URL and EVOLUTION_INSTANCE_ID and EVOLUTION_API_KEY):
        return
    final_url = (url_override or PUBLIC_WEBHOOK_URL or "").strip()
    if not final_url:
        return
    body = {
        "enabled": True,
        "url": final_url,
        "webhookByEvents": bool(webhook_by_events),
        "webhookBase64": bool(webhook_base64),
        "events": events or ["MESSAGE"],
    }
    headers = {
        "Content-Type": "application/json",
        "apikey": EVOLUTION_API_KEY,
    }
    logger.info("whatsapp.ensure_webhook", extra={"url": body.get("url"), "events": body.get("events")})
    resp = requests.post(_endpoint_set_webhook(), json=body, headers=headers, timeout=15)
    resp.raise_for_status()


