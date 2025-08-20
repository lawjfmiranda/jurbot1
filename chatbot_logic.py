import json
import os
import re
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Dict, List, Optional
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

import logging
import database
import calendar_service
import notification_service
import ai_service


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
        "3️⃣  Informações de contato e horário\n"
        "4️⃣  Meus agendamentos"
    )
    return menu


def greeting_text(number: Optional[str] = None) -> str:
    base = FAQ.get("boas_vindas", WELCOME_FALLBACK)
    if number:
        try:
            client = database.get_client_by_whatsapp(number)
            name = (client and client.get("full_name")) or None
            if name:
                first = str(name).split(" ")[0]
                return base.replace("Olá!", f"Olá, {first}!")
        except Exception:
            pass
    return base


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
    if contains_any(message, ["cancelar", "cancelamento", "desmarcar", "remarcar"]):
        return "CANCEL"
    # aceita variações: "1", "1.", "opção 1", etc
    m = re.search(r"\b([1-4])\b", message.strip())
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


def _weekday_pt_br(dt: datetime) -> str:
    names = [
        "segunda-feira",
        "terça-feira",
        "quarta-feira",
        "quinta-feira",
        "sexta-feira",
        "sábado",
        "domingo",
    ]
    name = names[dt.weekday()]
    return name[0].upper() + name[1:]


class Chatbot:
    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

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
            self.logger.info("chatbot.state", extra={"user": number, "state": current, "intent": intent})
            if intent == "LEAD":
                conversation_state.set(number, "state", "LEAD_Q_START")
                return [
                    "Entendi. Para que eu possa te ajudar da melhor forma e direcionar ao advogado especialista, preciso fazer algumas perguntas rÃ¡pidas, tudo bem?",
                    "Qual Ã© o seu nome completo?",
                ]
            if intent == "CANCEL":
                conversation_state.set(number, "state", "CANCEL_LOOKUP")
                return ["Certo, vamos cancelar sua consulta. Informe a data (dd/mm/aaaa) ou digite 'todas' para listar as próximas do seu número."]
            if contains_any(message, ["adiantar", "antecipar", "mais cedo"]):
                # tentar slots mais próximos dos próximos 3 dias
                existing = database.get_future_meetings_by_number(number, datetime.utcnow())
                if not existing:
                    conversation_state.set(number, "state", "SCHEDULING_PREF_PERIOD")
                    return ["Não encontrei consulta ativa. Vamos agendar uma nova. Você prefere de manhã ou à tarde?"]
                data["pref_period"] = data.get("pref_period", "indiferente")
                data["reschedule_event_id"] = existing[0]["google_calendar_event_id"]
                conversation_state.set(number, "data", data)
                conversation_state.set(number, "state", "SCHEDULING_SHOW_SLOTS")
                fresh = calendar_service.get_next_available_slots(
                    preferred_period=(data.get("pref_period") if data.get("pref_period") != "indiferente" else None),
                    start_offset_days=0,
                )
                conversation_state.set(number, "data", {**data, "slots": [(s.isoformat(), e.isoformat()) for s, e in fresh[:3]]})
                return ["Encontrei opções mais próximas:", present_slots(fresh)]
            # Tentar classificar pergunta jurídica e responder com IA
            if len(message) >= 15:
                try:
                    ai = ai_service.extract_intent(message)
                except Exception:
                    ai = {"intent": None}
                if ai.get("intent") == "duvida_juridica" and ai.get("confidence", 0) >= 0.6:
                    area = ai.get("area") or "Direito do Trabalho"
                    reply = ai_service.legal_answer(area, message)
                    reply += "\n\nSe quiser, posso te ajudar a agendar uma consulta. Digite 2."
                    return [reply]
            if intent in ("GREET", "UNKNOWN"):
                conversation_state.set(number, "state", "FREE_CHAT")
                return [greeting_text(number)]

        if current == "FREE_CHAT":
            # Comandos rápidos
            if contains_any(message, ["menu"]):
                conversation_state.set(number, "state", "MENU")
                return [build_menu()]
            if contains_any(message, ["cancelar", "desmarcar", "remarcar"]):
                conversation_state.set(number, "state", "CANCEL_LOOKUP")
                return ["Certo, vamos cancelar sua consulta. Informe a data (dd/mm/aaaa) ou digite 'todas' para listar as próximas do seu número."]
            # Opções 1-4 funcionam aqui também
            m = re.search(r"\b([1-4])\b", message)
            if m:
                conversation_state.set(number, "state", "MENU")
                return self.handle_incoming_message(number, m.group(1))
            # IA como padrão
            if len(message) >= 8:
                try:
                    ai = ai_service.extract_intent(message)
                except Exception:
                    ai = {"intent": None}
                if ai.get("intent") == "duvida_juridica" and ai.get("confidence", 0) >= 0.5:
                    area = ai.get("area") or "Direito do Trabalho"
                    reply = ai_service.legal_answer(area, message)
                    reply += "\n\nSe quiser, posso te ajudar a agendar uma consulta. Digite 2."
                    return [reply]
            # Se nada foi entendido, sugerir menu
            return [ai_service.small_talk_reply("Posso te ajudar com alguma dúvida ou agendar uma consulta. Se preferir, digite 'menu'.")]

        if current == "MENU":
            intent = detect_intent(message)
            self.logger.info("chatbot.state", extra={"user": number, "state": current, "intent": intent})
            if intent == "CANCEL":
                conversation_state.set(number, "state", "CANCEL_LOOKUP")
                return ["Certo, vamos cancelar sua consulta. Informe a data (dd/mm/aaaa) ou digite 'todas' para listar."]
            if intent == "MENU_CHOICE":
                selected = re.search(r"\b([1-4])\b", message).group(1)
                if selected == "1":
                    return [format_areas_atuacao()]
                if selected == "2":
                    # Verifica se já há consulta futura para este número
                    existing = [r for r in database.get_future_meetings(datetime.utcnow()) if r["whatsapp_number"] == number]
                    if existing:
                        when = datetime.fromisoformat(str(existing[0]["meeting_datetime"]).replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
                        return [
                            f"Você já possui uma consulta marcada para {when}.\n",
                            "Se desejar, posso verificar uma data anterior para tentar adiantar, ou podemos cancelar e reagendar.",
                            "Digite: 'adiantar' para procurar datas mais próximas, ou 'cancelar' para cancelar a atual.",
                        ]
                    # Puxar dados existentes do cliente e evitar perguntar de novo
                    client = database.get_client_by_whatsapp(number)
                    client_full_name = (client and client.get("full_name")) or None
                    client_email = (client and client.get("email")) or None
                    if client_full_name:
                        data["full_name"] = client_full_name
                    if client_email:
                        data["email"] = client_email
                    conversation_state.set(number, "data", data)
                    if not client_full_name:
                        conversation_state.set(number, "state", "SCHEDULING_ASK_NAME")
                        return ["Antes de seguirmos, poderia me informar seu nome completo?"]
                    conversation_state.set(number, "state", "SCHEDULING_PREF_PERIOD")
                    return [
                        "Perfeito! Para agilizar, você prefere ser atendido de manhã ou à tarde? (responda: manhã, tarde ou indiferente)",
                        "Se desejar, responda 'voltar' para retornar ao menu."
                    ]
                if selected == "3":
                    return [format_informacoes_gerais()]
                if selected == "4":
                    # listar próximos agendamentos do número
                    rows = database.get_future_meetings(datetime.utcnow())
                    rows = [r for r in rows if r["whatsapp_number"] == number]
                    if not rows:
                        return ["Você não possui consultas futuras registradas."]
                    items = []
                    tz = ZoneInfo(os.getenv("TIMEZONE", "America/Sao_Paulo")) if ZoneInfo else None
                    for idx, r in enumerate(rows[:5], start=1):
                        dt_utc = datetime.fromisoformat(str(r["meeting_datetime"]).replace("Z", "+00:00"))
                        when = dt_utc.astimezone(tz).strftime("%d/%m/%Y %H:%M") if tz else dt_utc.strftime("%d/%m/%Y %H:%M")
                        items.append(f"{idx}️⃣  {when}")
                    return ["Seus próximos agendamentos:\n" + "\n".join(items) + "\n\nPara cancelar, digite 'cancelar'."]
            # Se o usuário escreveu um texto livre, tentar IA para dúvida jurídica
            if len(message) >= 15:
                try:
                    ai = ai_service.extract_intent(message)
                except Exception:
                    ai = {"intent": None}
                if ai.get("intent") == "duvida_juridica" and ai.get("confidence", 0) >= 0.6:
                    area = ai.get("area") or "Direito do Trabalho"
                    reply = ai_service.legal_answer(area, message)
                    reply += "\n\nCaso queira, digite 2 para agendar uma consulta sobre isso."
                    return [reply]
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
            lines = [ai_service.small_talk_reply("Escolha a data desejada:")]
            for idx, d in enumerate(days, start=1):
                lines.append(f"{idx}️⃣  {_weekday_pt_br(d)}, {d.strftime('%d/%m/%Y')}")
            lines.append("\nResponda com 1 a 5. Digite 'voltar' para o menu.")
            return ["\n".join(lines)]

        if current == "SCHEDULING_ASK_NAME":
            name = message.strip()
            if len(name) < 3:
                return ["Por favor, informe seu nome completo."]
            database.upsert_client(whatsapp_number=number, full_name=name)
            data["full_name"] = name
            conversation_state.set(number, "data", data)
            conversation_state.set(number, "state", "SCHEDULING_PREF_PERIOD")
            return [
                "Obrigado! Para agilizar, você prefere ser atendido de manhã ou à tarde? (responda: manhã, tarde ou indiferente)",
            ]

        if current == "SCHEDULING_CHOOSE_DATE":
            if message.lower() == "voltar":
                conversation_state.set(number, "state", "FREE_CHAT")
                return [greeting_text(number)]
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
            return [ai_service.small_talk_reply(present_slots(slots)), "Digite 'mais' para ver outras datas, ou 'voltar' para o menu."]

        if current in ("LEAD_Q_START", "ASK_NAME"):
            # Store full name
            data["full_name"] = message
            conversation_state.set(number, "data", data)
            conversation_state.set(number, "state", "ASK_EMAIL")
            try:
                database.upsert_client(whatsapp_number=number, full_name=message)
            except Exception:
                pass
            return ["Perfeito. Qual Ã© o seu e-mail para contato?"]

        if current == "ASK_EMAIL":
            # simple email validation
            email = message.strip()
            if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                return ["Poderia verificar o e-mail informado? Parece nÃ£o estar no formato correto. Ex: nome@dominio.com"]
            data["email"] = email
            conversation_state.set(number, "data", data)
            # persist email junto ao cliente (merge)
            try:
                database.upsert_client(whatsapp_number=number, email=email)
            except Exception:
                pass
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
            return [ai_service.small_talk_reply(thank_you), present_slots(slots)]

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
                return [ai_service.small_talk_reply(present_slots(fresh)), "Digite 'mais' para ver outras datas, ou 'voltar' para o menu."]

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
                    return [ai_service.small_talk_reply(present_slots(fresh)), "Digite 'mais' para ver outras datas, ou 'voltar' para o menu."]
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
                # Build rich description
                desc_lines = []
                if data.get("case_summary"):
                    desc_lines.append(f"Resumo: {data.get('case_summary')}")
                desc_lines.append(f"WhatsApp: +{number}")
                if data.get("email"):
                    desc_lines.append(f"E-mail: {data.get('email')}")
                description_value = "\n".join(desc_lines) if desc_lines else "Consulta inicial"

                title_value = f"Consulta Inicial - {full_name} - +{number}"
                try:
                    if data.get("reschedule_event_id"):
                        calendar_service.update_event(
                            event_id=data["reschedule_event_id"],
                            title=title_value,
                            start_datetime=start_dt,
                            end_datetime=end_dt,
                            description=description_value,
                            attendees=[data.get("email")] if data.get("email") else None,
                        )
                        database.update_meeting_time_by_event(data["reschedule_event_id"], start_dt)
                    else:
                        event_id = calendar_service.create_event(
                            title=title_value,
                            start_datetime=start_dt,
                            end_datetime=end_dt,
                            description=description_value,
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
                except Exception:
                    # Informe falha e mantenha estado para tentar novamente
                    return [
                        "Tivemos um problema ao confirmar no calendário agora. Já estamos cientes e vamos ajustar. Você pode tentar novamente escolhendo 1, 2 ou 3, ou digitar 'voltar' para retornar ao menu.",
                    ]
                # Após confirmar, volta para conversa livre
                conversation_state.set(number, "state", "FREE_CHAT")
                conversation_state.set(number, "data", {})
                tz = ZoneInfo(os.getenv("TIMEZONE", "America/Sao_Paulo")) if ZoneInfo else None
                local_start = start_dt.astimezone(tz) if tz and start_dt.tzinfo else start_dt
                confirm = (
                    "Perfeito! Sua consulta foi marcada.\n"
                    f"Data e hora: {local_start.strftime('%d/%m/%Y %H:%M')}\n"
                    "Você receberá um lembrete 24 horas antes. Se precisar ajustar, é só me avisar."
                )
                confirm = ai_service.small_talk_reply(confirm)
                follow = ai_service.small_talk_reply("Posso te ajudar com mais alguma dúvida? Se quiser ver opções novamente, digite 'menu'.")
                return [confirm, follow]
            else:
                return ["NÃ£o entendi sua escolha. Responda com 1, 2 ou 3 para selecionar um horÃ¡rio."]

        # Cancelamento: localizar e cancelar
        if current == "CANCEL_LOOKUP":
            query = message.strip().lower()
            rows = []
            if query == "todas":
                rows = database.get_future_meetings(datetime.utcnow())
            else:
                try:
                    dt = datetime.strptime(query, "%d/%m/%Y")
                    start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                    end = dt.replace(hour=23, minute=59, second=59, microsecond=0)
                    rows = database.get_meetings_between(start, end)
                except Exception:
                    return ["Formato de data inválido. Envie como dd/mm/aaaa ou 'todas'."]
            rows = [r for r in rows if r["whatsapp_number"] == number]
            if not rows:
                return ["Não encontrei consultas futuras para este número. Digite 2 para agendar ou 'adiantar' para buscar datas mais próximas se já tiver uma consulta."]
            items = []
            tz = ZoneInfo(os.getenv("TIMEZONE", "America/Sao_Paulo")) if ZoneInfo else None
            for idx, r in enumerate(rows[:5], start=1):
                dt_utc = datetime.fromisoformat(str(r["meeting_datetime"]).replace("Z", "+00:00"))
                when = dt_utc.astimezone(tz).strftime("%d/%m/%Y %H:%M") if tz else dt_utc.strftime("%d/%m/%Y %H:%M")
                items.append(f"{idx}️⃣  {when}")
            conversation_state.set(number, "state", "CANCEL_CHOOSE")
            conversation_state.set(number, "data", {"cancel_rows": [dict(r) for r in rows[:5]]})
            return ["Qual consulta deseja cancelar?\n" + "\n".join(items) + "\n\nResponda com 1 a 5 ou digite 'voltar' para o menu."]

        if current == "CANCEL_CHOOSE":
            if message.strip().lower() == "voltar":
                conversation_state.set(number, "state", "MENU")
                return [build_menu()]
            m = re.search(r"\b([1-5])\b", message)
            if not m:
                return ["Responda com um número de 1 a 5, ou 'voltar' para o menu."]
            idx = int(m.group(1)) - 1
            rows = state.get("data", {}).get("cancel_rows", [])
            if idx < 0 or idx >= len(rows):
                return ["Opção inválida. Tente novamente (1–5)."]
            chosen = rows[idx]
            event_id = chosen.get("google_calendar_event_id")
            try:
                calendar_service.delete_event(event_id)
                database.update_meeting_status(chosen["id"], "CANCELADA")
            except Exception:
                pass
            conversation_state.clear(number)
            return ["Consulta cancelada com sucesso. Se desejar, podemos agendar outro horário. Digite 2 para ver opções."]

        # Default fallback: mantém conversa natural
        conversation_state.set(number, "state", "FREE_CHAT")
        return [greeting_text()]


