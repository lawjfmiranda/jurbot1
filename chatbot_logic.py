import json
import os
import re
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Dict, List, Optional

import database
import calendar_service
import notification_service


FAQ_PATH = os.getenv("FAQ_PATH", os.path.join(os.path.dirname(__file__), "faq.json"))


def load_faq() -> dict:
    if not os.path.exists(FAQ_PATH):
        return {}
    with open(FAQ_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


FAQ = load_faq()


def normalize_number(whatsapp_number: str) -> str:
    digits = re.sub(r"\D+", "", whatsapp_number)
    return digits


def contains_any(text: str, keywords: List[str]) -> bool:
    text_lower = text.lower()
    return any(k.lower() in text_lower for k in keywords)


class ConversationState:
    def __init__(self) -> None:
        self.state_by_user: Dict[str, Dict[str, Any]] = {}
        self.lock = Lock()

    def get(self, user: str) -> Dict[str, Any]:
        with self.lock:
            return self.state_by_user.setdefault(user, {"state": "INIT", "data": {}})

    def set(self, user: str, key: str, value: Any) -> None:
        with self.lock:
            entry = self.state_by_user.setdefault(user, {"state": "INIT", "data": {}})
            entry[key] = value

    def clear(self, user: str) -> None:
        with self.lock:
            if user in self.state_by_user:
                del self.state_by_user[user]


conversation_state = ConversationState()


WELCOME_FALLBACK = (
    "Olá! 🤝 Sou a JustIA, assistente virtual do Escritório. Como posso te ajudar hoje?"
)


def build_menu() -> str:
    boas_vindas = FAQ.get("boas_vindas", WELCOME_FALLBACK)
    menu = (
        f"{boas_vindas}\n\n"
        "Escolha uma opção:\n"
        "1️⃣  Conhecer nossas áreas de atuação\n"
        "2️⃣  Agendar uma consulta\n"
        "3️⃣  Informações de contato e horário"
    )
    return menu


HELP_KEYWORDS = [
    "demit", "demiss", "acidente", "pensao", "pensão", "inventar",
    "processo", "ajuda", "advog", "audien", "prazo", "urgente", "guarda", "rescis",
]

GREET_KEYWORDS = ["oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "menu", "help"]


def detect_intent(message: str) -> str:
    if contains_any(message, HELP_KEYWORDS):
        return "LEAD"
    if contains_any(message, GREET_KEYWORDS):
        return "GREET"
    # aceita variações: "1", "1.", "opção 1", etc
    m = re.search(r"\b([1-3])\b", message.strip())
    if m:
        return "MENU_CHOICE"
    return "UNKNOWN"


def format_areas_atuacao() -> str:
    areas = FAQ.get("areas_atuacao", {})
    if not areas:
        return "Nossas áreas de atuação estão temporariamente indisponíveis."
    lines = ["Áreas de Atuação:"]
    for area, desc in areas.items():
        lines.append(f"• {area}: {desc}")
    lines.append("\nPosso te ajudar com mais alguma coisa? Digite 2️⃣ para agendar uma consulta.")
    return "\n".join(lines)


def format_informacoes_gerais() -> str:
    info = FAQ.get("informacoes_gerais", {})
    endereco = info.get("endereco", "Endereço não informado.")
    horario = info.get("horario", "Horário não informado.")
    return (
        f"📍 Endereço: {endereco}\n"
        f"🕘 Horário de funcionamento: {horario}\n\n"
        "Deseja agendar uma consulta? Digite 2️⃣."
    )


def present_slots(slots: List[tuple[datetime, datetime]]) -> str:
    if not slots:
        return "No momento não há horários disponíveis. Posso tentar novamente mais tarde."
    lines = ["Temos os seguintes horários livres:"]
    for idx, (start, _end) in enumerate(slots[:3], start=1):
        lines.append(f"{idx}️⃣  {start.strftime('%d/%m/%Y')} às {start.strftime('%H:%M')}")
    lines.append("\nResponda com o número da opção desejada (1, 2 ou 3).")
    return "\n".join(lines)


class Chatbot:
    def __init__(self) -> None:
        pass

    def handle_incoming_message(self, raw_number: str, message: str) -> List[str]:
        number = normalize_number(raw_number)
        state = conversation_state.get(number)
        current = state.get("state", "INIT")
        data = state.get("data", {})
        message = message.strip()

        # Initialize DB client record if not exists
        database.upsert_client(whatsapp_number=number)

        # Flow control
        if current == "INIT":
            intent = detect_intent(message)
            if intent == "LEAD":
                conversation_state.set(number, "state", "LEAD_Q_START")
                return [
                    "Entendi. Para que eu possa te ajudar da melhor forma e direcionar ao advogado especialista, preciso fazer algumas perguntas rÃ¡pidas, tudo bem?",
                    "Qual Ã© o seu nome completo?",
                ]
            if intent in ("GREET", "UNKNOWN"):
                conversation_state.set(number, "state", "MENU")
                return [build_menu()]

        if current == "MENU":
            intent = detect_intent(message)
            if intent == "MENU_CHOICE":
                selected = re.search(r"\b([1-3])\b", message).group(1)
                if selected == "1":
                    return [format_areas_atuacao()]
                if selected == "2":
                    conversation_state.set(number, "state", "SCHEDULING_PREF_PERIOD")
                    return [
                        "Perfeito! Para agilizar, você prefere ser atendido de manhã ou à tarde? (responda: manhã, tarde ou indiferente)",
                        "Se desejar, responda 'voltar' para retornar ao menu."
                    ]
                if selected == "3":
                    return [format_informacoes_gerais()]
            # Fallback to menu
            return [build_menu()]

        if current == "SCHEDULING_PREF_PERIOD":
            pref = message.strip().lower()
            if "manh" in pref:
                pref_val = "manha"
            elif "tard" in pref:
                pref_val = "tarde"
            else:
                pref_val = "indiferente"
            data["pref_period"] = pref_val
            conversation_state.set(number, "data", data)
            # Após escolher período, exibimos opções de datas úteis
            conversation_state.set(number, "state", "SCHEDULING_CHOOSE_DATE")
            days = calendar_service.get_next_business_days(count=5)
            data["dates"] = [d.strftime('%Y-%m-%d') for d in days]
            conversation_state.set(number, "data", data)
            lines = ["Escolha a data desejada:"]
            for idx, d in enumerate(days, start=1):
                lines.append(f"{idx}️⃣  {d.strftime('%A, %d/%m/%Y')}")
            lines.append("\nResponda com 1 a 5. Digite 'voltar' para o menu.")
            return ["\n".join(lines)]

        if current == "SCHEDULING_CHOOSE_DATE":
            if message.lower() == "voltar":
                conversation_state.set(number, "state", "MENU")
                return [build_menu()]
            m = re.search(r"\b([1-5])\b", message)
            data = state.get("data", {})
            dates = data.get("dates", [])
            if not m or not dates:
                return ["Por favor, responda com um número de 1 a 5 para escolher a data, ou 'voltar' para o menu."]
            idx = int(m.group(1)) - 1
            if idx < 0 or idx >= len(dates):
                return ["Opção inválida. Responda com 1 a 5."]
            selected_date_str = dates[idx]
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d')
            try:
                slots = calendar_service.get_available_slots_for_date(
                    target_date=selected_date,
                    preferred_period=("manhã" if data.get("pref_period") == "manha" else ("tarde" if data.get("pref_period") == "tarde" else None))
                )
            except Exception:
                slots = []
            conversation_state.set(number, "state", "SCHEDULING_SHOW_SLOTS")
            conversation_state.set(number, "data", {**data, "slots": [(s.isoformat(), e.isoformat()) for s, e in slots[:3]]})
            return [present_slots(slots), "Digite 'mais' para ver outras datas, ou 'voltar' para o menu."]

        if current in ("LEAD_Q_START", "ASK_NAME"):
            # Store full name
            data["full_name"] = message
            conversation_state.set(number, "data", data)
            conversation_state.set(number, "state", "ASK_EMAIL")
            return ["Perfeito. Qual Ã© o seu e-mail para contato?"]

        if current == "ASK_EMAIL":
            # simple email validation
            email = message.strip()
            if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                return ["Poderia verificar o e-mail informado? Parece nÃ£o estar no formato correto. Ex: nome@dominio.com"]
            data["email"] = email
            conversation_state.set(number, "data", data)
            conversation_state.set(number, "state", "ASK_SUMMARY")
            return ["Obrigado. Poderia descrever brevemente o seu caso, de forma objetiva?"]

        if current == "ASK_SUMMARY":
            data["case_summary"] = message
            conversation_state.set(number, "data", data)
            conversation_state.set(number, "state", "ASK_URGENCY")
            return [
                "Para entendermos a urgÃªncia, vocÃª possui algum prazo legal ou audiÃªncia se aproximando? (sim/nÃ£o)",
            ]

        if current == "ASK_URGENCY":
            urgency_text = message.lower()
            high_priority = contains_any(urgency_text, ["sim", "prazo", "audiÃªn", "audien", "urgente"])
            priority = "ALTA" if high_priority else "MÃ‰DIA"
            data["lead_priority"] = priority
            # Persist client
            client_id = database.upsert_client(
                whatsapp_number=number,
                full_name=data.get("full_name"),
                email=data.get("email"),
                case_summary=data.get("case_summary"),
                lead_priority=priority,
            )
            conversation_state.set(number, "data", {**data, "client_id": client_id})
            # Internal notification
            subject = f"NOVO LEAD QUALIFICADO (PRIORIDADE: {priority})"
            content = (
                f"Nome: {data.get('full_name') or ''}\n"
                f"Contato: {number} / {data.get('email') or ''}\n"
                f"Resumo do Caso: {data.get('case_summary') or ''}\n"
                f"UrgÃªncia: {'Possui prazo/audiÃªncia/urgÃªncia' if priority=='ALTA' else 'Sem urgÃªncia prÃ³xima'}\n"
            )
            try:
                notification_service.send_internal_notification(subject, content)
            except Exception:
                pass
            # Transition to scheduling
            conversation_state.set(number, "state", "SCHEDULING_SHOW_SLOTS")
            try:
                slots = calendar_service.get_next_available_slots()
            except Exception:
                slots = []
            conversation_state.set(number, "data", {**data, "client_id": client_id, "slots": [(s.isoformat(), e.isoformat()) for s, e in slots[:3]]})

            nome = data.get("full_name") or "Cliente"
            thank_you = (
                f"Obrigado, {nome}. Suas informaÃ§Ãµes foram recebidas e nossa equipe jÃ¡ foi notificada. "
                "Para agilizar seu atendimento, vamos marcar uma consulta inicial?"
            )
            return [thank_you, present_slots(slots)]

        if current == "SCHEDULING_SHOW_SLOTS":
            # Expect choice 1-3
            if message.lower() == "voltar":
                conversation_state.set(number, "state", "MENU")
                return [build_menu()]
            data = state.get("data", {})
            if message.lower() == "mais":
                # Buscar próximos 3 slots após +2 dias
                try:
                    fresh = calendar_service.get_next_available_slots(
                        preferred_period=(data.get("pref_period") if data.get("pref_period") != "indiferente" else None),
                        start_offset_days=2,
                    )
                except Exception:
                    fresh = []
                conversation_state.set(number, "data", {**data, "slots": [(s.isoformat(), e.isoformat()) for s, e in fresh[:3]]})
                return [present_slots(fresh), "Digite 'mais' para ver outras datas, ou 'voltar' para o menu."]

            choice_match = re.search(r"\b([1-3])\b", message)
            slots = data.get("slots", [])
            if not slots:
                # Try fetch again if empty
                try:
                    fresh = calendar_service.get_next_available_slots(
                        preferred_period=(data.get("pref_period") if data.get("pref_period") != "indiferente" else None)
                    )
                except Exception:
                    fresh = []
                if fresh:
                    conversation_state.set(number, "data", {**data, "slots": [(s.isoformat(), e.isoformat()) for s, e in fresh[:3]]})
                    return [present_slots(fresh), "Digite 'mais' para ver outras datas, ou 'voltar' para o menu."]
                return ["No momento não há horários disponíveis para agendamento. Posso verificar novamente mais tarde ou coletar sua preferência de horários."]
            if choice_match and slots:
                idx = int(choice_match.group(1)) - 1
                try:
                    start_iso, end_iso = slots[idx]
                except IndexError:
                    return ["OpÃ§Ã£o invÃ¡lida. Por favor, responda com 1, 2 ou 3."]

                start_dt = datetime.fromisoformat(start_iso)
                end_dt = datetime.fromisoformat(end_iso)
                client = database.get_client_by_whatsapp(number)
                full_name = (
                    (client["full_name"] if client is not None else None)
                    or data.get("full_name")
                    or number
                )
                event_id = calendar_service.create_event(
                    title=f"Consulta Inicial - {full_name}",
                    start_datetime=start_dt,
                    end_datetime=end_dt,
                    description=data.get("case_summary") or "Consulta inicial",
                    attendees=[data.get("email")] if data.get("email") else None,
                )
                # Persist meeting
                client_id = (client and client["id"]) or data.get("client_id") or database.upsert_client(number)
                database.add_meeting(
                    client_id=client_id,
                    google_calendar_event_id=event_id,
                    meeting_datetime=start_dt,
                    status="MARCADA",
                )
                conversation_state.clear(number)
                confirm = (
                    "Perfeito! Sua consulta foi marcada.\n"
                    f"Data e hora: {start_dt.strftime('%d/%m/%Y %H:%M')}\n"
                    "VocÃª receberÃ¡ um lembrete 24 horas antes. Se precisar ajustar, Ã© sÃ³ me avisar."
                )
                return [confirm]
            else:
                return ["NÃ£o entendi sua escolha. Responda com 1, 2 ou 3 para selecionar um horÃ¡rio."]

        # Default fallback
        conversation_state.set(number, "state", "MENU")
        return [build_menu()]


