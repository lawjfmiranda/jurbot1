"""
AI Orchestrator - Gerencia toda a conversação através de IA com linguagem natural
"""
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging
import requests
import asyncio

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

import database
import calendar_service
import notification_service
import ai_service
from utils.lead_qualification import lead_qualifier

logger = logging.getLogger(__name__)


class N8NIntegration:
    """Integração com n8n para automações avançadas."""
    
    def __init__(self, n8n_base_url: str = None):
        self.base_url = n8n_base_url or os.getenv("N8N_BASE_URL", "http://localhost:5678")
        self.logger = logging.getLogger(__name__)
    
    def trigger_workflow(self, workflow_name: str, data: dict) -> dict:
        """Dispara um workflow específico no n8n."""
        try:
            webhook_url = f"{self.base_url}/webhook/{workflow_name}"
            
            self.logger.info(f"🔥 Triggering n8n workflow: {workflow_name}")
            self.logger.debug(f"📤 Data sent to n8n: {data}")
            
            response = requests.post(
                webhook_url,
                json=data,
                timeout=30,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                self.logger.info(f"✅ n8n workflow success: {workflow_name}")
                return {"success": True, "data": result}
            else:
                self.logger.error(f"❌ n8n workflow failed: {response.status_code} - {response.text}")
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"🔌 n8n connection error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            self.logger.error(f"💥 n8n unexpected error: {e}")
            return {"success": False, "error": str(e)}
    
    def classify_case_for_workflow(self, message: str) -> str:
        """Classifica o tipo de caso para escolher o workflow correto."""
        message_lower = message.lower()
        
        # Casos de Direito de Família
        if any(word in message_lower for word in ["divórcio", "separação", "guarda", "pensão", "casamento"]):
            return "familia"
        
        # Casos de Acidente/Seguro
        elif any(word in message_lower for word in ["acidente", "bateu", "colisão", "seguro", "danos"]):
            return "acidente"
        
        # Casos Trabalhistas
        elif any(word in message_lower for word in ["trabalho", "demissão", "rescisão", "fgts", "salário"]):
            return "trabalhista"
        
        # Casos Criminais
        elif any(word in message_lower for word in ["agressão", "violência", "ameaça", "roubo", "furto"]):
            return "criminal"
        
        # Casos Cíveis Gerais
        elif any(word in message_lower for word in ["contrato", "dívida", "cobrança", "indenização"]):
            return "civel"
        
        # Default: qualificação geral
        return "geral"


class AIConversationManager:
    """Gerencia conversação completa através de IA natural."""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        # Importar config aqui para evitar import circular
        try:
            from config import AppConfig
            config = AppConfig()
            self.n8n = N8NIntegration(config.n8n.base_url) if config.n8n.enabled else None
        except ImportError:
            self.logger.warning("Config não encontrado, usando configuração padrão para n8n")
            self.n8n = N8NIntegration()
    
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
        if current_state in ["SCHED_NAME", "SCHED_PERIOD", "SCHED_DATE", "SCHED_SLOT", "SCHED_TIME"]:
            self.logger.info(f"Continuing schedule flow in state: {current_state}")
            # Forçar intent=schedule para continuar fluxo
            decision = {"intent": "schedule", "action": "continue_schedule", "response": ""}
        elif current_state in ["QUALIFY"]:
            self.logger.info(f"Continuing qualification flow in state: {current_state}")
            # Forçar intent=qualify para continuar qualificação
            decision = {"intent": "qualify", "action": "continue_qualify", "response": ""}
        elif current_state == "SCHEDULE_AFTER_QUALIFY":
            self.logger.info("Transitioning from qualification to scheduling")
            # Cliente quer agendar após qualificação
            if any(word in message.lower() for word in ["sim", "quero", "vamos", "ok", "agendar"]):
                decision = {"intent": "schedule", "action": "start_schedule", "response": ""}
            else:
                decision = {"intent": "small_talk", "action": "chat", "response": ""}
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
        
        prompt = f"""Você é JustIA, assistente PROFISSIONAL do JM ADVOGADOS. Use linguagem formal e respeitosa.

CONTEXTO ATUAL:
{context}

MENSAGEM DO CLIENTE:
{message}

REGRAS DE CLASSIFICAÇÃO:
- Use "greeting" APENAS se for a PRIMEIRA mensagem do cliente (saudação inicial)
- Se ESTADO ATUAL = SCHED_NAME/SCHED_PERIOD/SCHED_DATE/SCHED_SLOT/SCHED_TIME: continue o fluxo de agendamento
- Use "schedule" APENAS se cliente quer INICIAR novo agendamento E estado = FREE
- Use "cancel" se cliente quer cancelar/desmarcar
- Use "list_meetings" APENAS se cliente quer VER/CONSULTAR/VERIFICAR seus agendamentos existentes
- Use "info" APENAS para informações do escritório (endereço, telefone, horário de funcionamento)
- Use "small_talk" para: perguntas sobre VALORES/PREÇOS/CUSTOS, despedidas, confirmações, agradecimentos
- Use "legal" APENAS para dúvidas teóricas/gerais sobre direito
- **Use "qualify" para casos REAIS e ESPECÍFICOS que a pessoa está vivendo**
- NUNCA interrompa um processo de agendamento em andamento
- Para respostas como "ok", "perfeito", "obrigado", "tchau" → use "small_talk"

DIFERENÇA CRÍTICA ENTRE "legal" e "qualify":
- "legal" = dúvida teórica ("Como funciona divórcio?", "O que é pensão?")
- "qualify" = caso REAL ("Quero me divorciar", "Sofri acidente", "Estou sendo ameaçada")

SEMPRE use "qualify" quando:
- Cliente conta um problema que ACONTECEU com ele
- Descreve situação ATUAL que está vivendo
- Quer RESOLVER um problema específico
- Menciona valores, datas, nomes, detalhes factuais
- Fala em primeira pessoa sobre seu caso

EXEMPLOS DE CLASSIFICAÇÃO:
  * "quando é minha consulta?" → list_meetings
  * "qual meu agendamento?" → list_meetings  
  * "onde fica o escritório?" → info
  * "qual o telefone?" → info
  * "quanto custa a consulta?" → small_talk
  * "qual o valor?" → small_talk
  * "quero saber o preço" → small_talk

EXEMPLOS CRÍTICOS "legal" vs "qualify":
  * "Como funciona um divórcio?" → legal (dúvida teórica)
  * "Quero me divorciar do meu marido" → qualify (caso real)
  * "O que é pensão alimentícia?" → legal (dúvida teórica) 
  * "Meu ex não paga pensão" → qualify (caso real)
  * "Posso processar por acidente?" → legal (dúvida teórica)
  * "Sofri um acidente semana passada" → qualify (caso real)
  * "Como funciona medida protetiva?" → legal (dúvida teórica)
  * "Meu ex está me ameaçando" → qualify (caso real)

TOM PROFISSIONAL:
- Use "Senhor/Senhora" quando apropriado
- Evite gírias e linguagem informal
- Seja cordial mas profissional
- Mantenha formalidade adequada a um escritório de advocacia

Responda APENAS com JSON:
{{
  "intent": "greeting|schedule|cancel|legal|info|areas|list_meetings|small_talk|qualify",
  "action": "acao_especifica",
  "response": "resposta natural e profissional"
}}"""
        
        try:
            result = ai_service._call_gemini_api(prompt)
            self.logger.info(f"AI Raw Response for '{message[:50]}...': {result[:200]}...")
            
            # Extrair JSON
            match = re.search(r'\{.*"intent".*\}', result, re.DOTALL)
            if match:
                decision = json.loads(match.group())
                self.logger.info(f"AI Parsed Decision: {decision}")
                return decision
        except Exception as e:
            self.logger.error(f"Erro IA: {e}")
        
        # Fallback
        fallback_decision = self._fallback_intent(message)
        self.logger.info(f"Using Fallback Decision: {fallback_decision} for message: '{message[:50]}...'")
        return fallback_decision
    
    def _fallback_intent(self, message: str) -> Dict[str, Any]:
        """Detecta intenção básica se IA falhar."""
        msg = message.lower()
        
        # PRIORIDADE: Casos específicos que precisam qualificação
        qualify_indicators = [
            # Primeira pessoa - problemas reais
            "sofri", "tive", "estou", "fui", "me aconteceu", "aconteceu comigo",
            "meu ex", "minha ex", "meu marido", "minha esposa", "meu caso",
            "preciso resolver", "quero processar", "quero me divorciar",
            "estou sendo", "me ameaçou", "não paga", "não pagou",
            # Contextos específicos com detalhes
            "acidente", "bateu", "bateram", "colisão", "seguro",
            "violência", "agressão", "ameaça", "proteção", "delegacia",
            "separação", "divórcio", "guarda", "pensão", "casa", "bens",
            "preso", "prisão", "processo", "audiência", "condenação"
        ]
        
        # Verificar se contém indicadores de qualificação
        if any(indicator in msg for indicator in qualify_indicators):
            return {"intent": "qualify", "action": "start_qualify", "response": ""}
        
        # Palavras de agendamento
        if any(w in msg for w in ["agendar", "marcar", "consulta", "gostaria de agendar"]):
            return {"intent": "schedule", "action": "start_schedule", "response": "Vamos agendar sua consulta!"}
        
        # Palavras de cancelamento
        if any(w in msg for w in ["cancelar", "desmarcar", "remarcar"]):
            return {"intent": "cancel", "action": "start_cancel", "response": "Vou verificar seus agendamentos."}
        
        # Saudações específicas (apenas se for realmente uma saudação inicial)
        if any(w in msg for w in ["olá", "oi", "bom dia", "boa tarde", "boa noite"]) and len(msg) < 20:
            return {"intent": "greeting", "action": "greet", "response": ""}
        
        # Dúvidas jurídicas teóricas (apenas perguntas genéricas)
        theoretical_questions = ["como funciona", "o que é", "como é", "qual é", "pode explicar"]
        if any(q in msg for q in theoretical_questions):
            return {"intent": "legal", "action": "legal_answer", "response": ""}
        
        # Mensagens longas provavelmente são casos para qualificar
        if len(message) > 50:
            return {"intent": "qualify", "action": "start_qualify", "response": ""}
        
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
            "small_talk": self._handle_chat,
            "qualify": self._handle_qualification  # Novo handler
        }
        
        handler = handlers.get(intent, self._handle_chat)
        return handler(user_number, message, state, client, decision)
    
    def _handle_greeting(self, user_number: str, message: str, state: Dict,
                        client: Optional[Dict], decision: Dict) -> Dict[str, Any]:
        """Saudação personalizada para clientes novos e recorrentes."""
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
                
                # Verificar se é cliente recorrente (tem consultas passadas)
                try:
                    past_meetings = database.get_meetings_by_client(client["id"])
                    if past_meetings and len(past_meetings) > 0:
                        greeting = f"Olá novamente, {name}! É um prazer ter você de volta ao JM ADVOGADOS."
                    else:
                        greeting = base.replace("Olá!", f"Olá, {name}!")
                except:
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
            try:
                has_name = bool(client and client["full_name"] if client else False)
            except (KeyError, TypeError):
                has_name = False
            self.logger.info(f"Schedule start: client={client}, has_name={has_name}")
            
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
                slots = calendar_service.get_available_slots_for_date(selected, duration_minutes=60, preferred_period=period)
                
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
                    try:
                        client_id = client["id"] if client else database.upsert_client(user_number, full_name=name)
                    except (KeyError, TypeError):
                        client_id = database.upsert_client(user_number, full_name=name)
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
        
        # Detectar perguntas sobre valores
        msg_lower = message.lower()
        value_keywords = ["valor", "preço", "custo", "quanto", "custa", "cobr", "pag"]
        
        if any(keyword in msg_lower for keyword in value_keywords):
            response = ("Os valores das consultas podem variar conforme a complexidade do caso. "
                       "Para informações precisas sobre honorários, recomendo que confirme "
                       "diretamente com nosso setor financeiro durante o agendamento ou "
                       "entre em contato pelo telefone do escritório.")
        else:
            response = decision.get("response")
            if not response:
                # Usar contexto mais profissional
                context = "Sou assistente do JM ADVOGADOS. Posso ajudar com informações jurídicas ou agendar consultas."
                response = ai_service.small_talk_reply(
                    context,
                    user_text=message,
                    max_chars=300
                )
        
        return {"replies": [response], "new_state": {"state": "FREE", "data": {}}}
    
    def _handle_qualification(self, user_number: str, message: str, state: Dict,
                             client: Optional[Dict], decision: Dict) -> Dict[str, Any]:
        """Qualificação inteligente de leads por área."""
        
        current = state.get("state", "FREE")
        data = state.get("data", {})
        
        if current == "FREE":
            # 🔥 INTEGRAÇÃO N8N: Disparar workflow de qualificação (se habilitado)
            if self.n8n:
                case_type = self.n8n.classify_case_for_workflow(message)
                
                # Enviar dados para n8n processar
                n8n_data = {
                    "user_number": user_number,
                    "message": message,
                    "case_type": case_type,
                    "timestamp": datetime.now().isoformat(),
                    "client_info": {
                        "name": client.get("name") if client else None,
                        "email": client.get("email") if client else None
                    }
                }
                
                # Disparar workflow n8n
                n8n_result = self.n8n.trigger_workflow(f"qualificacao_{case_type}", n8n_data)
                
                if n8n_result.get("success"):
                    self.logger.info(f"🎯 n8n workflow triggered successfully for case: {case_type}")
                    # Se n8n retornou resposta específica, usar ela
                    if n8n_result.get("data", {}).get("response"):
                        response = n8n_result["data"]["response"]
                        return {
                            "replies": [response],
                            "new_state": {**state, "state": "FREE"}
                        }
                else:
                    self.logger.warning(f"⚠️ n8n workflow failed for case: {case_type}")
            else:
                self.logger.debug("n8n disabled, using traditional qualification")
            
            # Identificar área para qualificação (fallback se n8n falhar)
            try:
                intent_result = ai_service.extract_intent(message)
                area = intent_result.get("area")
                
                if not area:
                    # Tentar identificar área por palavras-chave
                    msg_lower = message.lower()
                    area_keywords = {
                        "Responsabilidade Civil": ["indenização", "acidente", "dano", "prejuízo"],
                        "Direito das Famílias": ["divórcio", "guarda", "pensão", "separação"],
                        "Ação Penal": ["crime", "processo", "polícia", "preso"],
                        "Medida Protetiva": ["violência", "ameaça", "proteção", "agressão"]
                    }
                    
                    for area_name, keywords in area_keywords.items():
                        if any(kw in msg_lower for kw in keywords):
                            area = area_name
                            break
                
                if not area:
                    return self._handle_legal(user_number, message, state, client, decision)
                
                # Começar qualificação
                questions = lead_qualifier.get_questions_for_area(area)
                if not questions:
                    return self._handle_legal(user_number, message, state, client, decision)
                
                data["qualification_area"] = area
                data["questions"] = questions
                data["current_question"] = 0
                data["answers"] = {}
                
                first_question = questions[0]
                
                response_parts = [
                    f"Entendi que você tem uma questão de {area}.",
                    "Para te ajudar da melhor forma, vou fazer algumas perguntas específicas, ok?",
                    "",
                    f"📋 {first_question['question']}"
                ]
                
                if "options" in first_question:
                    response_parts.append("")
                    for i, option in enumerate(first_question["options"], 1):
                        response_parts.append(f"{i}. {option}")
                
                return {
                    "replies": ["\n".join(response_parts)],
                    "new_state": {"state": "QUALIFY", "data": data}
                }
                
            except Exception as e:
                self.logger.error(f"Erro na qualificação: {e}")
                return self._handle_legal(user_number, message, state, client, decision)
        
        elif current == "QUALIFY":
            # Processar resposta da qualificação
            area = data.get("qualification_area")
            questions = data.get("questions", [])
            current_q_idx = data.get("current_question", 0)
            answers = data.get("answers", {})
            
            if current_q_idx >= len(questions):
                # Qualificação completa
                return self._complete_qualification(user_number, area, answers, data)
            
            current_question = questions[current_q_idx]
            question_id = current_question["id"]
            
            # Processar resposta
            if "options" in current_question:
                # Pergunta de múltipla escolha
                try:
                    choice_num = int(message.strip())
                    if 1 <= choice_num <= len(current_question["options"]):
                        answer = current_question["options"][choice_num - 1]
                    else:
                        return {
                            "replies": [f"Por favor, escolha um número de 1 a {len(current_question['options'])}."],
                            "new_state": state
                        }
                except ValueError:
                    # Tentativa de resposta em texto livre
                    answer = message.strip()
            else:
                # Pergunta aberta
                answer = message.strip()
            
            answers[question_id] = answer
            
            # Verificar se há pergunta condicional
            response_parts = []
            if "conditional" in current_question:
                condition = current_question["conditional"]
                if condition["if"] in answer:
                    response_parts.append(condition["then"])
            
            # Follow-up da pergunta atual
            if "follow_up" in current_question:
                response_parts.append(current_question["follow_up"])
            
            # Próxima pergunta
            data["current_question"] = current_q_idx + 1
            data["answers"] = answers
            
            if data["current_question"] < len(questions):
                next_question = questions[data["current_question"]]
                response_parts.extend(["", f"📋 {next_question['question']}"])
                
                if "options" in next_question:
                    response_parts.append("")
                    for i, option in enumerate(next_question["options"], 1):
                        response_parts.append(f"{i}. {option}")
                
                return {
                    "replies": ["\n".join(response_parts)],
                    "new_state": {"state": "QUALIFY", "data": data}
                }
            else:
                # Qualificação completa
                return self._complete_qualification(user_number, area, answers, data)
        
        # Default
        return self._handle_chat(user_number, message, state, client, decision)
    
    def _complete_qualification(self, user_number: str, area: str, answers: Dict, data: Dict) -> Dict[str, Any]:
        """Completa o processo de qualificação."""
        
        # Calcular score e urgência
        score = lead_qualifier.calculate_lead_score(area, answers)
        urgency = lead_qualifier.check_urgency(area, answers)
        
        # Salvar dados do lead qualificado no banco
        try:
            # Atualizar cliente com dados coletados
            case_summary = f"Área: {area}\nScore: {score}/10\nRespostas: {answers}"
            priority = "ALTA" if urgency["is_urgent"] or score >= 8 else ("MÉDIA" if score >= 5 else "BAIXA")
            
            database.upsert_client(
                whatsapp_number=user_number,
                case_summary=case_summary,
                lead_priority=priority
            )
            
            # Notificar equipe
            try:
                summary = lead_qualifier.generate_summary(area, answers)
                import notification_service
                notification_service.send_internal_notification(
                    f"🎯 Lead Qualificado - {area} (Score: {score}/10)",
                    summary
                )
            except Exception as e:
                self.logger.error(f"Erro ao notificar equipe: {e}")
        
        except Exception as e:
            self.logger.error(f"Erro ao salvar qualificação: {e}")
        
        # Resposta personalizada baseada no score e urgência
        response_parts = [
            "✅ Obrigado pelas informações! Analisei seu caso e posso te ajudar."
        ]
        
        if urgency["is_urgent"]:
            if urgency["urgency_level"] == "critical":
                response_parts.extend([
                    "",
                    "🚨 **SITUAÇÃO URGENTE DETECTADA**",
                    f"Recomendo contato imediato: {urgency['recommended_action']}",
                    "",
                    "Vou te conectar com um advogado especialista agora mesmo.",
                    "Quer que eu agende uma consulta para hoje ainda?"
                ])
            else:
                response_parts.extend([
                    "",
                    "⚡ Identifiquei urgência no seu caso.",
                    "Vou priorizar seu atendimento.",
                    "",
                    "Posso agendar uma consulta para os próximos dias?"
                ])
        elif score >= 8:
            response_parts.extend([
                "",
                "🎯 Seu caso tem alta viabilidade jurídica!",
                "Temos experiência sólida em casos similares.",
                "",
                "Gostaria de agendar uma consulta para discutirmos a estratégia?"
            ])
        elif score >= 5:
            response_parts.extend([
                "",
                "📋 Vamos analisar melhor seu caso.",
                "Há possibilidades interessantes para explorar.",
                "",
                "Que tal marcarmos uma consulta para avaliarmos juntos?"
            ])
        else:
            response_parts.extend([
                "",
                "📝 Seu caso precisa de uma análise mais detalhada.",
                "Na consulta posso te dar orientações mais precisas.",
                "",
                "Vamos marcar um horário para conversarmos?"
            ])
        
        return {
            "replies": ["\n".join(response_parts)],
            "new_state": {"state": "SCHEDULE_AFTER_QUALIFY", "data": {"qualification_complete": True, "area": area, "score": score}}
        }
    
    def _weekday(self, dt: datetime) -> str:
        """Dia da semana em PT."""
        days = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        return days[dt.weekday()]


# Instância global
ai_manager = AIConversationManager()
