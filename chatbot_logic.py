"""
Módulo de lógica do chatbot - Simplificado para delegar tudo à IA
"""
import logging
import re
from threading import Lock
from typing import Any, Dict, List

import database
import ai_orchestrator


def normalize_number(whatsapp_number: str) -> str:
    """Normaliza número de WhatsApp removendo caracteres não numéricos."""
    digits = re.sub(r"\D+", "", whatsapp_number)
    return digits


class ConversationState:
    """Gerencia estado da conversa para cada usuário."""
    
    def __init__(self) -> None:
        self.state_by_user: Dict[str, Dict[str, Any]] = {}
        self.lock = Lock()

    def get(self, user: str) -> Dict[str, Any]:
        """Obtém estado da conversa do usuário."""
        with self.lock:
            return self.state_by_user.setdefault(user, {"state": "FREE", "data": {}})

    def set(self, user: str, key: str, value: Any) -> None:
        """Define valor no estado da conversa."""
        with self.lock:
            entry = self.state_by_user.setdefault(user, {"state": "FREE", "data": {}})
            entry[key] = value

    def clear(self, user: str) -> None:
        """Limpa estado da conversa do usuário."""
        with self.lock:
            if user in self.state_by_user:
                del self.state_by_user[user]


# Instância global do estado da conversa
conversation_state = ConversationState()


class Chatbot:
    """Classe principal do chatbot que delega processamento para IA."""
    
    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def handle_incoming_message(self, raw_number: str, message: str) -> List[str]:
        """
        Processa mensagem usando o AI Orchestrator para conversação natural completa.
        
        Args:
            raw_number: Número do WhatsApp (pode conter formatação)
            message: Mensagem recebida do usuário
            
        Returns:
            Lista de mensagens de resposta
        """
        # Normalizar número
        number = normalize_number(raw_number)
        
        # Obter estado atual da conversa
        state = conversation_state.get(number)
        
        # Limpar mensagem
        message = message.strip()
        
        # Garantir que cliente existe no banco
        database.upsert_client(whatsapp_number=number)
        
        # Delegar processamento para o AI Orchestrator
        try:
            result = ai_orchestrator.ai_manager.process(number, message, state)
        except Exception as e:
            self.logger.error(f"Erro ao processar mensagem com IA: {e}")
            return ["Desculpe, tive um problema ao processar sua mensagem. Por favor, tente novamente."]
        
        # Atualizar estado da conversa
        new_state = result.get("new_state", state)
        conversation_state.set(number, "state", new_state.get("state", "FREE"))
        conversation_state.set(number, "data", new_state.get("data", {}))
        
        # Retornar respostas
        replies = result.get("replies", ["Desculpe, não consegui processar sua mensagem."])
        
        # Log para debug detalhado
        self.logger.info(f"AI Orchestrator result: {result}")
        self.logger.info(f"Extracted replies: {replies}")
        self.logger.info(
            f"Mensagem processada para {number}: estado={new_state.get('state')}, "
            f"respostas={len(replies)}"
        )
        
        return replies
