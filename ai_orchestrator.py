import os
from typing import Any, Dict, Optional

import ai_service


SCHEDULE_KEYWORDS = [
    "agendar", "marcar", "consulta", "agendamento", "agenda", "agende", "quero consulta", "quero agendar",
]


def _wants_schedule(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in SCHEDULE_KEYWORDS)


def decide(user_number: str, message: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """Decide next high-level action using IA, constrained to firm's areas.

    Returns a dict with keys:
      - agenda: bool (start scheduling flow?)
      - reply: optional[str] (message to send)
      - area: optional[str] (legal area inferred)
    """
    message = (message or "").strip()
    if not message:
        return {"agenda": False, "reply": None}

    # 1) If user explicitly asks to schedule, honor immediately
    if _wants_schedule(message):
        return {"agenda": True, "reply": None}

    # 2) Try IA intent classification
    try:
        intent = ai_service.extract_intent(message)
    except Exception:
        intent = {"intent": None}

    if (intent.get("intent") == "duvida_juridica" and intent.get("confidence", 0) >= 0.5):
        area = intent.get("area") or ai_service.guess_area(message) or "Responsabilidade Civil"
        answer = ai_service.legal_answer(area, message)
        # CTA sutil para agendar
        answer += "\n\nSe quiser, posso agendar uma consulta. Diga: 'quero agendar'."
        return {"agenda": False, "reply": answer, "area": area}

    # 3) Small talk / dúvidas gerais sem caráter jurídico
    small = ai_service.small_talk_reply(
        "Posso te ajudar com isso. Se preferir, também posso agendar uma consulta para conversarmos com mais calma.",
        user_text=message,
        max_chars=260,
    )
    return {"agenda": False, "reply": small}


