"""
AI Orchestrator - Gerencia toda a conversação através de IA com linguagem natural
"""
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

import database
import calendar_service
import notification_service
import ai_service

logger = logging.getLogger(__name__)


class AIConversationManager:
    """Gerencia conversação completa através de IA natural."""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def process(self, user_number: str, message: str, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processa mensagem usando IA para toda a conversação.
        Returns: {"replies": [...], "new_state": {...}}
        """
        message = (message or "").strip()
        if not message:
            return {"replies": ["Desculpe, não entendi. Pode repetir?"], "new_state": state}
        
        # Buscar contexto do cliente
        client = database.get_client_by_whatsapp(user_number)
        context = self._build_context(user_number, client, state)
        self.logger.info(f"Context for {user_number}: {context[:200]}...")
        
        # Se está em processo de agendamento, continuar automaticamente
        current_state = state.get("state", "FREE")
        if current_state in ["SCHED_NAME", "SCHED_PERIOD", "SCHED_DATE", "SCHED_TIME"]:
            self.logger.info(f"Continuing schedule flow in state: {current_state}")
            # Forçar intent=schedule para continuar fluxo
            decision = {"intent": "schedule", "action": "continue_schedule", "response": ""}
        else:
            # IA decide ação e resposta
            decision = self._ai_decide(message, context)
            self.logger.info(f"AI Decision: {decision} for message: '{message[:50]}...'")
        
        # Executar ação determinística se necessário
        result = self._execute(decision, user_number, message, state, client)
        
        return result
    
    def _build_context(self, user_number: str, client: Optional[Dict], state: Dict[str, Any]) -> str:
        """Constrói contexto completo para a IA."""
        parts = []
        
        # Info do cliente
        if client:
            try:
                if client["full_name"]:
                    parts.append(f"Cliente: {client['full_name']}")
                if client["email"]:
                    parts.append(f"Email: {client['email']}")
            except (KeyError, TypeError):
                pass
        
        # Agendamentos existentes
        try:
            meetings = database.get_future_meetings(datetime.utcnow())
            user_meetings = [m for m in meetings if m["whatsapp_number"] == user_number]
            if user_meetings:
                next_meet = user_meetings[0]
                dt = datetime.fromisoformat(str(next_meet["meeting_datetime"]).replace("Z", "+00:00"))
                parts.append(f"Tem consulta em: {dt.strftime('%d/%m %H:%M')}")
        except:
            pass
        
        # Estado atual da conversa (CRÍTICO para IA!)
        current = state.get("state", "FREE")
        data = state.get("data", {})
        
        if current != "FREE":
            parts.append(f"ESTADO ATUAL: {current}")
            if data:
                parts.append(f"Dados em progresso: {data}")
        
        if data.get("slots"):
            parts.append(f"Slots disponíveis: {len(data['slots'])}")
        
        return "\n".join(parts) if parts else "Cliente novo"
    
    def _ai_decide(self, message: str, context: str) -> Dict[str, Any]:
        """IA decide ação baseada em mensagem e contexto."""
        
        prompt = f"""Você é JustIA, assistente do JM ADVOGADOS. Analise o contexto e decida a ação apropriada.

CONTEXTO ATUAL:
{context}

MENSAGEM DO CLIENTE:
{message}

REGRAS IMPORTANTES:
- Use "greeting" APENAS se for a PRIMEIRA mensagem do cliente (saudação inicial)
- Se ESTADO ATUAL = SCHED_NAME/SCHED_PERIOD/SCHED_DATE/SCHED_TIME: continue o fluxo de agendamento
- Use "schedule" APENAS se cliente quer INICIAR novo agendamento E estado = FREE
- Use "cancel" se cliente quer cancelar/desmarcar
- Use "legal" para dúvidas jurídicas
- Use "small_talk" para conversas casuais ou continuação de conversa
- NUNCA interrompa um processo de agendamento em andamento
- Se já coletando dados (nome, período, etc), continue coletando

Responda APENAS com JSON:
{{
  "intent": "greeting|schedule|cancel|legal|info|areas|list_meetings|small_talk",
  "action": "acao_especifica",
  "response": "resposta natural"
}}"""
        
        try:
            result = ai_service._call_gemini_api(prompt)
            # Extrair JSON
            match = re.search(r'\{.*"intent".*\}', result, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            self.logger.error(f"Erro IA: {e}")
        
        # Fallback
        return self._fallback_intent(message)
    
    def _fallback_intent(self, message: str) -> Dict[str, Any]:
        """Detecta intenção básica se IA falhar."""
        msg = message.lower()
        
        # Palavras de agendamento
        if any(w in msg for w in ["agendar", "marcar", "consulta", "gostaria de agendar"]):
            return {"intent": "schedule", "action": "start_schedule", "response": "Vamos agendar sua consulta!"}
        
        # Palavras de cancelamento
        if any(w in msg for w in ["cancelar", "desmarcar", "remarcar"]):
            return {"intent": "cancel", "action": "start_cancel", "response": "Vou verificar seus agendamentos."}
        
        # Saudações específicas (apenas se for realmente uma saudação inicial)
        if any(w in msg for w in ["olá", "oi", "bom dia", "boa tarde", "boa noite"]) and len(msg) < 20:
            return {"intent": "greeting", "action": "greet", "response": ""}
        
        # Dúvidas jurídicas (mensagens mais longas com contexto jurídico)
        if len(message) > 30 and any(w in msg for w in ["dúvida", "duvida", "problema", "caso", "processo", "ajuda"]):
            return {"intent": "legal", "action": "legal_answer", "response": ""}
        
        # Default: small talk
        return {"intent": "small_talk", "action": "chat", "response": "Como posso ajudar?"}
    
    def _execute(self, decision: Dict, user_number: str, message: str, 
                 state: Dict, client: Optional[Dict]) -> Dict[str, Any]:
        """Executa ação decidida pela IA."""
        
        intent = decision.get("intent", "small_talk")
        action = decision.get("action", "")
        response = decision.get("response", "")
        
        # Mapear intent para handler
        handlers = {
            "greeting": self._handle_greeting,
            "schedule": self._handle_schedule,
            "cancel": self._handle_cancel,
            "legal": self._handle_legal,
            "info": self._handle_info,
            "areas": self._handle_areas,
            "list_meetings": self._handle_list,
            "small_talk": self._handle_chat
        }
        
        handler = handlers.get(intent, self._handle_chat)
        return handler(user_number, message, state, client, decision)
    
    def _handle_greeting(self, user_number: str, message: str, state: Dict,
                        client: Optional[Dict], decision: Dict) -> Dict[str, Any]:
        """Saudação personalizada."""
        import json
        try:
            with open("faq.json", "r", encoding="utf-8") as f:
                FAQ = json.load(f)
        except:
            FAQ = {}
        base = FAQ.get("boas_vindas", "Olá! Sou JustIA do JM ADVOGADOS.")
        
        try:
            if client and client["full_name"]:
                name = client["full_name"].split()[0]
                greeting = base.replace("Olá!", f"Olá, {name}!")
            else:
                greeting = base
        except (KeyError, TypeError):
            greeting = base
        
        greeting += "\n\nComo posso ajudar? Posso tirar dúvidas jurídicas, agendar consultas ou fornecer informações."
        
        return {"replies": [greeting], "new_state": {"state": "FREE", "data": {}}}
    
    def _handle_schedule(self, user_number: str, message: str, state: Dict,
                        client: Optional[Dict], decision: Dict) -> Dict[str, Any]:
        """Gerencia agendamento via conversa natural."""
        
        current = state.get("state", "FREE")
        data = state.get("data", {})
        
        # Verificar se já tem consulta
        meetings = database.get_future_meetings(datetime.utcnow())
        user_meetings = [m for m in meetings if m["whatsapp_number"] == user_number]
        
        if user_meetings and current == "FREE":
            meet = user_meetings[0]
            dt = datetime.fromisoformat(str(meet["meeting_datetime"]).replace("Z", "+00:00"))
            return {
                "replies": [
                    f"Você já tem consulta em {dt.strftime('%d/%m às %H:%M')}.",
                    "Quer remarcar ou cancelar?"
                ],
                "new_state": state
            }
        
        # Fluxo de agendamento natural
        if current == "FREE":
            # Iniciar agendamento
            self.logger.info(f"Schedule start: client={client}, has_name={bool(client and client.get('full_name') if client else False)}")
            
            try:
                if client and client["full_name"] and client["full_name"].strip():
                    data["full_name"] = client["full_name"]
                    self.logger.info(f"Using existing name: {client['full_name']}")
                    return {
                        "replies": [
                            f"Ótimo, {client['full_name'].split()[0]}!",
                            "Você prefere manhã ou tarde? Ou qualquer horário serve?"
                        ],
                        "new_state": {"state": "SCHED_PERIOD", "data": data}
                    }
            except (KeyError, TypeError) as e:
                self.logger.info(f"No existing name found: {e}")
                pass
            
            # Se não tem nome, pedir nome
            self.logger.info("Requesting name for new schedule")
            return {
                "replies": ["Vamos agendar! Primeiro, qual seu nome completo?"],
                "new_state": {"state": "SCHED_NAME", "data": data}
            }
        
        elif current == "SCHED_NAME":
            # Coletar nome
            name = message.strip()
            self.logger.info(f"Collecting name: '{name}' for user {user_number}")
            
            if len(name) < 3:
                return {
                    "replies": ["Por favor, me diga seu nome completo."],
                    "new_state": state
                }
            
            # Salvar nome no banco
            try:
                database.upsert_client(whatsapp_number=user_number, full_name=name)
                self.logger.info(f"Name saved to DB: {name} for {user_number}")
            except Exception as e:
                self.logger.error(f"Error saving name to DB: {e}")
            
            data["full_name"] = name
            return {
                "replies": [f"Prazer, {name.split()[0]}! Prefere manhã, tarde ou qualquer horário?"],
                "new_state": {"state": "SCHED_PERIOD", "data": data}
            }
        
        elif current == "SCHED_PERIOD":
            # Período preferido
            msg = message.lower()
            if "manh" in msg:
                data["period"] = "manha"
            elif "tard" in msg:
                data["period"] = "tarde"
            else:
                data["period"] = "any"
            
            # Buscar datas
            days = calendar_service.get_next_business_days(count=5)
            data["dates"] = [d.strftime('%Y-%m-%d') for d in days]
            
            lines = ["Estas são as datas disponíveis:"]
            for i, d in enumerate(days, 1):
                lines.append(f"{i}. {d.strftime('%d/%m')} ({self._weekday(d)})")
            lines.append("Qual você prefere? (responda 1-5)")
            
            return {
                "replies": ["\n".join(lines)],
                "new_state": {"state": "SCHED_DATE", "data": data}
            }
        
        elif current == "SCHED_DATE":
            # Escolher data
            match = re.search(r'\b([1-5])\b', message)
            if not match or not data.get("dates"):
                return {
                    "replies": ["Por favor, escolha um número de 1 a 5."],
                    "new_state": state
                }
            
            idx = int(match.group(1)) - 1
            dates = data["dates"]
            if 0 <= idx < len(dates):
                selected = datetime.strptime(dates[idx], '%Y-%m-%d')
                
                # Buscar slots
                period = "manhã" if data.get("period") == "manha" else ("tarde" if data.get("period") == "tarde" else None)
                slots = calendar_service.get_available_slots_for_date(selected, period)
                
                if not slots:
                    return {
                        "replies": ["Sem horários nesta data. Escolha outra (1-5)."],
                        "new_state": state
                    }
                
                data["slots"] = [(s.isoformat(), e.isoformat()) for s, e in slots[:3]]
                
                lines = [f"Para {selected.strftime('%d/%m')}, tenho:"]
                for i, (s, _) in enumerate(slots[:3], 1):
                    lines.append(f"{i}. {s.strftime('%H:%M')}")
                lines.append("Qual horário? (1-3)")
                
                return {
                    "replies": ["\n".join(lines)],
                    "new_state": {"state": "SCHED_SLOT", "data": data}
                }
        
        elif current == "SCHED_SLOT":
            # Confirmar horário
            match = re.search(r'\b([1-3])\b', message)
            if not match or not data.get("slots"):
                return {
                    "replies": ["Escolha 1, 2 ou 3 para o horário."],
                    "new_state": state
                }
            
            idx = int(match.group(1)) - 1
            slots = data["slots"]
            if 0 <= idx < len(slots):
                start_iso, end_iso = slots[idx]
                start = datetime.fromisoformat(start_iso)
                end = datetime.fromisoformat(end_iso)
                
                # Criar evento
                name = data.get("full_name") or user_number
                title = f"Consulta - {name}"
                
                try:
                    event_id = calendar_service.create_event(
                        title=title,
                        start_datetime=start,
                        end_datetime=end,
                        description=f"WhatsApp: {user_number}"
                    )
                    
                    # Salvar no banco
                    client_id = client["id"] if client else database.upsert_client(user_number, full_name=name)
                    database.add_meeting(client_id, event_id, start, "MARCADA")
                    
                    tz = ZoneInfo(os.getenv("TIMEZONE", "America/Sao_Paulo")) if ZoneInfo else None
                    local = start.astimezone(tz) if tz else start
                    
                    return {
                        "replies": [
                            f"✅ Consulta confirmada!",
                            f"📅 {local.strftime('%d/%m/%Y às %H:%M')}",
                            "📍 Av. Cerro Azul, 258, Zona 02, Maringá-PR",
                            "",
                            "Você receberá lembrete 24h antes. Posso ajudar em algo mais?"
                        ],
                        "new_state": {"state": "FREE", "data": {}}
                    }
                except Exception as e:
                    self.logger.error(f"Erro agendamento: {e}")
                    return {
                        "replies": ["Erro ao agendar. Tente novamente."],
                        "new_state": {"state": "FREE", "data": {}}
                    }
        
        # Default
        return self._handle_chat(user_number, message, state, client, decision)
    
    def _handle_cancel(self, user_number: str, message: str, state: Dict,
                      client: Optional[Dict], decision: Dict) -> Dict[str, Any]:
        """Cancelamento natural."""
        
        current = state.get("state", "FREE")
        data = state.get("data", {})
        
        if current == "FREE":
            # Buscar agendamentos
            meetings = database.get_future_meetings(datetime.utcnow())
            user_meetings = [m for m in meetings if m["whatsapp_number"] == user_number]
            
            if not user_meetings:
                return {
                    "replies": ["Você não tem consultas agendadas. Quer agendar uma?"],
                    "new_state": state
                }
            
            if len(user_meetings) == 1:
                meet = user_meetings[0]
                dt = datetime.fromisoformat(str(meet["meeting_datetime"]).replace("Z", "+00:00"))
                data["cancel_id"] = meet["id"]
                data["cancel_event"] = meet["google_calendar_event_id"]
                
                return {
                    "replies": [
                        f"Você tem consulta em {dt.strftime('%d/%m às %H:%M')}.",
                        "Confirma o cancelamento? (sim/não)"
                    ],
                    "new_state": {"state": "CANCEL_CONFIRM", "data": data}
                }
            
            # Múltiplas
            lines = ["Suas consultas:"]
            data["cancel_options"] = []
            for i, m in enumerate(user_meetings[:5], 1):
                dt = datetime.fromisoformat(str(m["meeting_datetime"]).replace("Z", "+00:00"))
                lines.append(f"{i}. {dt.strftime('%d/%m às %H:%M')}")
                data["cancel_options"].append({"id": m["id"], "event": m["google_calendar_event_id"]})
            lines.append("Qual cancelar? (1-5)")
            
            return {
                "replies": ["\n".join(lines)],
                "new_state": {"state": "CANCEL_SELECT", "data": data}
            }
        
        elif current == "CANCEL_SELECT":
            match = re.search(r'\b([1-5])\b', message)
            if match and data.get("cancel_options"):
                idx = int(match.group(1)) - 1
                opts = data["cancel_options"]
                if 0 <= idx < len(opts):
                    data["cancel_id"] = opts[idx]["id"]
                    data["cancel_event"] = opts[idx]["event"]
                    return {
                        "replies": ["Confirma cancelamento? (sim/não)"],
                        "new_state": {"state": "CANCEL_CONFIRM", "data": data}
                    }
        
        elif current == "CANCEL_CONFIRM":
            if "sim" in message.lower():
                try:
                    calendar_service.delete_event(data["cancel_event"])
                    database.update_meeting_status(data["cancel_id"], "CANCELADA")
                    return {
                        "replies": ["✅ Cancelado! Quer reagendar?"],
                        "new_state": {"state": "FREE", "data": {}}
                    }
                except:
                    pass
            elif "n" in message.lower():
                return {
                    "replies": ["Ok, mantive sua consulta. Posso ajudar em algo mais?"],
                    "new_state": {"state": "FREE", "data": {}}
                }
        
        return {
            "replies": ["Não entendi. Pode repetir?"],
            "new_state": state
        }
    
    def _handle_legal(self, user_number: str, message: str, state: Dict,
                     client: Optional[Dict], decision: Dict) -> Dict[str, Any]:
        """Resposta jurídica via IA."""
        
        try:
            intent = ai_service.extract_intent(message)
            area = intent.get("area") or ai_service.guess_area(message) or "Direito Civil"
            answer = ai_service.legal_answer(area, message)
            answer += "\n\nPara orientação detalhada, posso agendar uma consulta."
            
            return {"replies": [answer], "new_state": {"state": "FREE", "data": {}}}
        except:
            return self._handle_chat(user_number, message, state, client, decision)
    
    def _handle_info(self, user_number: str, message: str, state: Dict,
                    client: Optional[Dict], decision: Dict) -> Dict[str, Any]:
        """Informações do escritório."""
        import json
        try:
            with open("faq.json", "r", encoding="utf-8") as f:
                FAQ = json.load(f)
        except:
            FAQ = {}
        info = FAQ.get("informacoes_gerais", {})
        
        lines = ["📍 **JM ADVOGADOS**"]
        if info.get("endereco"):
            lines.append(f"Endereço: {info['endereco']}")
        if info.get("horario"):
            lines.append(f"Horário: {info['horario']}")
        if info.get("site"):
            lines.append(f"Site: {info['site']}")
        lines.append("\nPosso agendar uma consulta ou tirar dúvidas!")
        
        return {"replies": ["\n".join(lines)], "new_state": {"state": "FREE", "data": {}}}
    
    def _handle_areas(self, user_number: str, message: str, state: Dict,
                     client: Optional[Dict], decision: Dict) -> Dict[str, Any]:
        """Áreas de atuação."""
        import json
        try:
            with open("faq.json", "r", encoding="utf-8") as f:
                FAQ = json.load(f)
        except:
            FAQ = {}
        areas = FAQ.get("areas_atuacao", {})
        
        lines = ["📚 Nossas áreas:"]
        for area, desc in areas.items():
            lines.append(f"• {area}: {desc}")
        lines.append("\nQuer agendar consulta sobre alguma área?")
        
        return {"replies": ["\n".join(lines)], "new_state": {"state": "FREE", "data": {}}}
    
    def _handle_list(self, user_number: str, message: str, state: Dict,
                    client: Optional[Dict], decision: Dict) -> Dict[str, Any]:
        """Lista agendamentos."""
        
        meetings = database.get_future_meetings(datetime.utcnow())
        user_meetings = [m for m in meetings if m["whatsapp_number"] == user_number]
        
        if not user_meetings:
            return {
                "replies": ["Você não tem consultas agendadas. Quer agendar?"],
                "new_state": {"state": "FREE", "data": {}}
            }
        
        lines = ["📅 Suas consultas:"]
        for m in user_meetings:
            dt = datetime.fromisoformat(str(m["meeting_datetime"]).replace("Z", "+00:00"))
            lines.append(f"• {dt.strftime('%d/%m às %H:%M')}")
        lines.append("\nPrecisa remarcar ou cancelar?")
        
        return {"replies": ["\n".join(lines)], "new_state": {"state": "FREE", "data": {}}}
    
    def _handle_chat(self, user_number: str, message: str, state: Dict,
                    client: Optional[Dict], decision: Dict) -> Dict[str, Any]:
        """Conversa geral via IA."""
        
        response = decision.get("response")
        if not response:
            response = ai_service.small_talk_reply(
                "Posso ajudar com dúvidas jurídicas ou agendar consultas.",
                user_text=message,
                max_chars=300
            )
        
        return {"replies": [response], "new_state": {"state": "FREE", "data": {}}}
    
    def _weekday(self, dt: datetime) -> str:
        """Dia da semana em PT."""
        days = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        return days[dt.weekday()]


# Instância global
ai_manager = AIConversationManager()
