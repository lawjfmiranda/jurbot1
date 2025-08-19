import os
import requests


EVOLUTION_BASE_URL = os.getenv("EVOLUTION_API_BASE_URL", "")
EVOLUTION_INSTANCE_ID = os.getenv("EVOLUTION_INSTANCE_ID", "")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")


def _endpoint_send_text() -> str:
    # Common Evolution endpoint pattern
    base = EVOLUTION_BASE_URL.rstrip("/")
    return f"{base}/message/sendText/{EVOLUTION_INSTANCE_ID}"


def send_whatsapp_message(number: str, text: str) -> None:
    if not (EVOLUTION_BASE_URL and EVOLUTION_INSTANCE_ID and EVOLUTION_API_KEY):
        raise RuntimeError("Evolution API nÃ£o configurada. Defina EVOLUTION_API_BASE_URL, EVOLUTION_INSTANCE_ID, EVOLUTION_API_KEY.")

    payload = {
        "number": number,
        "text": text,
    }
    headers = {
        "Content-Type": "application/json",
        "apikey": EVOLUTION_API_KEY,
    }
    url = _endpoint_send_text()
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()


