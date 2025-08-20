import os
import json
import logging
import uuid
import contextvars
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

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s | %(req_id)s",
)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "req_id"):
            try:
                record.req_id = _request_id_var.get()
            except Exception:
                record.req_id = "-"
        return True


class RequestIdFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "req_id"):
            record.req_id = "-"
        return super().format(record)


def _install_req_id_formatter() -> None:
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        fmt = handler.formatter._fmt if handler.formatter else "%(asctime)s %(levelname)s %(name)s - %(message)s | %(req_id)s"
        datefmt = handler.formatter.datefmt if handler.formatter else None
        handler.setFormatter(RequestIdFormatter(fmt=fmt, datefmt=datefmt))
    for handler in list(app.logger.handlers):
        fmt = handler.formatter._fmt if handler.formatter else "%(asctime)s %(levelname)s %(name)s - %(message)s | %(req_id)s"
        datefmt = handler.formatter.datefmt if handler.formatter else None
        handler.setFormatter(RequestIdFormatter(fmt=fmt, datefmt=datefmt))


_req_filter = RequestIdFilter()
logging.getLogger().addFilter(_req_filter)
app.logger.addFilter(_req_filter)
_install_req_id_formatter()

# Context var para req_id
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("req_id", default="-")

# Rate limit simples em memória por número
_last_seen: dict[str, float] = {}
_MIN_INTERVAL_SECONDS = float(os.getenv("MIN_MSG_INTERVAL", "0.5"))


def _extract_number(payload: Dict[str, Any]) -> Optional[str]:
    # Prefer event-style contact id first (avoid using 'sender' which is the instance number)
    number: Optional[str] = None
    if isinstance(payload.get("data"), dict):
        data = payload["data"]
        # messages[0].key.remoteJid
        if isinstance(data.get("messages"), list) and data["messages"]:
            first = data["messages"][0]
            key = isinstance(first.get("key"), dict) and first.get("key") or {}
            number = key.get("remoteJid")
        if not number:
            key = isinstance(data.get("key"), dict) and data.get("key") or {}
            number = key.get("remoteJid") or data.get("remoteJid")
    # Fallbacks for other payload shapes
    if not number:
        number = (
            payload.get("number")
            or payload.get("from")
            or payload.get("chatId")
            or payload.get("remoteJid")
            or None  # do NOT use 'sender' as it may be the instance number
        )
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
        # messages[0].message
        if isinstance(data.get("messages"), list) and data["messages"]:
            msg = data["messages"][0].get("message") or {}
        else:
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


@app.route("/debug/echo", methods=["GET", "POST"])
def debug_echo():
    token = request.headers.get("X-Webhook-Token") or request.args.get("token")
    body = request.get_json(silent=True)
    try:
        raw = request.data.decode("utf-8") if request.data else ""
    except Exception:
        raw = ""
    app.logger.info(
        {
            "debug": "echo",
            "method": request.method,
            "path": request.path,
            "args": request.args.to_dict(flat=True),
            "headers_subset": {k: request.headers.get(k) for k in ["Content-Type", "User-Agent", "X-Webhook-Token", "Content-Length"]},
            "token": token,
            "json_keys": list(body.keys()) if isinstance(body, dict) else None,
            "raw_len": len(raw),
        }
    )
    return jsonify({"ok": True, "received": True})


@app.route("/webhook/evolution", methods=["POST"])
def evolution_webhook():
    # correlation id por requisição
    req_id = request.headers.get("X-Req-Id") or str(uuid.uuid4())
    # seta no contexto para ser capturado pelo filtro/formatter
    _token = _request_id_var.set(req_id)
    token = request.headers.get("X-Webhook-Token") or request.args.get("token")
    if token and "/" in token:
        token = token.split("/", 1)[0]
    if EVOLUTION_WEBHOOK_TOKEN and token != EVOLUTION_WEBHOOK_TOKEN:
        app.logger.warning("Webhook auth failed: missing/invalid token")
        return jsonify({"error": "unauthorized"}), 401

    body = request.get_json(silent=True)
    if body is None:
        try:
            body = json.loads(request.data.decode("utf-8")) if request.data else {}
        except Exception:
            body = {}
    app.logger.info(
        f"Webhook received type={type(body)} keys={list(body.keys()) if isinstance(body, dict) else 'n/a'}",
    )
    messages: List[Dict[str, Any]] = []

    # Evolution pode enviar eventos por mensagem (webhookByEvents) ou listas em 'messages'
    if isinstance(body, dict) and isinstance(body.get("messages"), list):
        messages = body["messages"]
    elif isinstance(body, dict) and body.get("event"):
        # Evento único
        messages = [body]
    else:
        messages = [body]

    app.logger.info(f"Webhook messages_count={len(messages)}")
    for idx, msg in enumerate(messages):
        # Ignore messages sent by our own instance (status updates, echoes)
        own = msg.get("fromMe") or msg.get("from_me")
        if own is None and isinstance(msg.get("data"), dict):
            own = msg["data"].get("key", {}).get("fromMe")
        if str(own) in ("True", "true", "1"):
            app.logger.debug(f"Ignored own message idx={idx}")
            continue
        number = _extract_number(msg)
        text = _extract_text(msg)
        if not number or not text:
            short = None
            try:
                short = json.dumps(msg)[:300]
            except Exception:
                short = str(msg)[:300]
            app.logger.info(
                f"Skipped msg idx={idx} number={number} text_len={(len(text) if text else 0)} payload={short}",
            )
            continue

        # rate limit
        import time
        now_s = time.time()
        last = _last_seen.get(number, 0.0)
        if now_s - last < _MIN_INTERVAL_SECONDS:
            app.logger.debug(f"Rate limited number={number}")
            continue
        _last_seen[number] = now_s

        app.logger.info(
            f"Incoming idx={idx} number={number} text='{text[:120]}'",
        )
        try:
            responses = chatbot.handle_incoming_message(number, text)
        except Exception as e:
            app.logger.exception("Error in chatbot logic")
            try:
                import notification_service
                notification_service.notify_error("Erro no webhook JustIA", f"Number: {number}\nError: {e}")
            except Exception:
                pass
            continue
        for r in responses:
            try:
                whatsapp_service.send_whatsapp_message(number, r)
                app.logger.info(
                    f"Sent reply to {number}: '{r[:120]}'",
                )
            except Exception:
                app.logger.exception(f"Failed to send WhatsApp message to {number}")

    try:
        return jsonify({"status": "received"})
    finally:
        # limpa req_id do contexto
        try:
            _request_id_var.reset(_token)
        except Exception:
            _request_id_var.set("-")


@app.route("/admin/clients", methods=["GET"])
def admin_clients():
    token = request.headers.get("X-Admin-Token") or request.args.get("token")
    if token != os.getenv("ADMIN_TOKEN"):
        return jsonify({"error": "unauthorized"}), 401
    q = request.args.get("q")
    rows = database.list_clients(q)
    return jsonify([
        {
            "id": r["id"],
            "whatsapp_number": r["whatsapp_number"],
            "full_name": r["full_name"],
            "email": r["email"],
            "lead_priority": r["lead_priority"],
            "created_at": r["creation_timestamp"],
        } for r in rows
    ])


@app.route("/admin/meetings", methods=["GET"])
def admin_meetings():
    token = request.headers.get("X-Admin-Token") or request.args.get("token")
    if token != os.getenv("ADMIN_TOKEN"):
        return jsonify({"error": "unauthorized"}), 401
    number = request.args.get("number")
    rows = database.list_meetings(whatsapp_number=number)
    return jsonify([
        {
            "id": r["id"],
            "whatsapp_number": r["whatsapp_number"],
            "full_name": r["full_name"],
            "event_id": r["google_calendar_event_id"],
            "when": r["meeting_datetime"],
            "status": r["status"],
        } for r in rows
    ])

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


