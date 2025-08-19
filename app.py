import os
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request

from dotenv import load_dotenv
import database
from chatbot_logic import Chatbot
import whatsapp_service
import scheduler as jobs_scheduler


EVOLUTION_WEBHOOK_TOKEN = os.getenv("EVOLUTION_WEBHOOK_TOKEN")


app = Flask(__name__)
chatbot = Chatbot()


def _extract_number(payload: Dict[str, Any]) -> Optional[str]:
    # Evolution variants
    number = (
        payload.get("number")
        or payload.get("from")
        or payload.get("chatId")
        or payload.get("remoteJid")
        or payload.get("sender")
    )
    # Event-style: payload.data.key.remoteJid
    if not number and isinstance(payload.get("data"), dict):
        data = payload["data"]
        key = isinstance(data.get("key"), dict) and data.get("key") or {}
        number = key.get("remoteJid") or data.get("remoteJid")
    if not number:
        return None
    # normalize patterns like 5511999999999@c.us
    if isinstance(number, str) and "@" in number:
        number = number.split("@", 1)[0]
    return number


def _extract_text(payload: Dict[str, Any]) -> Optional[str]:
    if "text" in payload and isinstance(payload["text"], dict):
        t = payload["text"].get("body") or payload["text"].get("text")
        if t:
            return str(t)
    # Event-style: payload.data.message
    if isinstance(payload.get("data"), dict):
        data = payload["data"]
        msg = data.get("message") or {}
        if isinstance(msg, dict):
            # conversation
            if msg.get("conversation"):
                return str(msg.get("conversation")).strip()
            # extendedTextMessage
            etm = msg.get("extendedTextMessage")
            if isinstance(etm, dict) and etm.get("text"):
                return str(etm.get("text")).strip()
            # image caption
            im = msg.get("imageMessage")
            if isinstance(im, dict) and im.get("caption"):
                return str(im.get("caption")).strip()
            # buttons response
            br = msg.get("buttonsResponseMessage")
            if isinstance(br, dict):
                if br.get("selectedDisplayText"):
                    return str(br.get("selectedDisplayText")).strip()
                if br.get("selectedId"):
                    return str(br.get("selectedId")).strip()
            # list response
            lr = msg.get("listResponseMessage")
            if isinstance(lr, dict):
                sel = lr.get("singleSelectReply")
                if isinstance(sel, dict) and sel.get("selectedRowId"):
                    return str(sel.get("selectedRowId")).strip()
    return str(
        payload.get("message")
        or payload.get("body")
        or payload.get("text")
        or payload.get("content")
        or ""
    ).strip()


@app.route("/health", methods=["GET"])  # Simple healthcheck
def health():
    return jsonify({"status": "ok"})


@app.route("/webhook/evolution", methods=["POST"])
def evolution_webhook():
    token = request.headers.get("X-Webhook-Token") or request.args.get("token")
    if EVOLUTION_WEBHOOK_TOKEN and token != EVOLUTION_WEBHOOK_TOKEN:
        return jsonify({"error": "unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    messages: List[Dict[str, Any]] = []

    # Evolution pode enviar eventos por mensagem (webhookByEvents) ou listas em 'messages'
    if isinstance(body, dict) and isinstance(body.get("messages"), list):
        messages = body["messages"]
    elif isinstance(body, dict) and body.get("event"):
        # Evento único
        messages = [body]
    else:
        messages = [body]

    for msg in messages:
        # Ignore messages sent by our own instance (status updates, echoes)
        own = msg.get("fromMe") or msg.get("from_me")
        if own is None and isinstance(msg.get("data"), dict):
            own = msg["data"].get("key", {}).get("fromMe")
        if str(own) in ("True", "true", "1"):
            continue
        number = _extract_number(msg)
        text = _extract_text(msg)
        if not number or not text:
            continue

        responses = chatbot.handle_incoming_message(number, text)
        for r in responses:
            try:
                whatsapp_service.send_whatsapp_message(number, r)
            except Exception as e:
                app.logger.error(f"Failed to send WhatsApp message to {number}: {e}")

    return jsonify({"status": "received"})


def create_app() -> Flask:
    load_dotenv()
    database.initialize_database()
    # Start scheduler background jobs
    jobs_scheduler.start_scheduler()
    return app


# Ensure app is initialized when imported by WSGI servers (e.g., Gunicorn)
application = create_app()


if __name__ == "__main__":
    # Avoid running scheduler twice with Flask reloader
    use_reloader = os.getenv("FLASK_ENV") == "development"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), use_reloader=use_reloader)


