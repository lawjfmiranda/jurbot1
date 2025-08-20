"""
Sistema de log seguro que mascarar dados sensíveis
"""
import json
import re
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SecureFormatter(logging.Formatter):
    """Formatter que remove automaticamente dados sensíveis dos logs."""
    
    # Padrões de dados sensíveis para mascarar
    SENSITIVE_PATTERNS = [
        # Números de telefone/WhatsApp
        (r'(\d{2,3})(\d{4,5})(\d{4})', r'\1****\3'),
        # Email (mantém primeira letra e domínio)
        (r'([a-zA-Z])[a-zA-Z0-9._%+-]*@([a-zA-Z0-9.-]+)', r'\1****@\2'),
        # CPF/CNPJ
        (r'(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})', r'\1.***.**-\4'),
        # Tokens/Keys (qualquer string > 20 chars alfanuméricos)
        (r'([a-zA-Z0-9]{8})[a-zA-Z0-9]{12,}([a-zA-Z0-9]{4})', r'\1****\2'),
    ]
    
    # Campos JSON que devem ser mascarados
    SENSITIVE_FIELDS = [
        'apikey', 'token', 'password', 'key', 'secret',
        'authorization', 'auth', 'credential', 'private_key',
        'whatsapp_number', 'phone', 'email', 'cpf', 'cnpj'
    ]
    
    def format(self, record: logging.LogRecord) -> str:
        """Formata log removendo dados sensíveis."""
        # Formatar normalmente primeiro
        formatted = super().format(record)
        
        # Mascarar padrões sensíveis
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            formatted = re.sub(pattern, replacement, formatted)
        
        return formatted


def mask_sensitive_data(data: Any, max_depth: int = 3) -> Any:
    """
    Mascara dados sensíveis em estruturas de dados complexas.
    
    Args:
        data: Dados a serem mascarados
        max_depth: Profundidade máxima para recursão
        
    Returns:
        Dados com informações sensíveis mascaradas
    """
    if max_depth <= 0:
        return "..."
    
    if isinstance(data, dict):
        masked = {}
        for key, value in data.items():
            key_lower = str(key).lower()
            
            # Verificar se é campo sensível
            is_sensitive = any(sensitive in key_lower for sensitive in [
                'apikey', 'token', 'password', 'key', 'secret',
                'authorization', 'auth', 'credential', 'private_key'
            ])
            
            if is_sensitive:
                if isinstance(value, str) and len(value) > 8:
                    masked[key] = f"{value[:4]}****{value[-4:]}"
                else:
                    masked[key] = "****"
            elif key_lower in ['whatsapp_number', 'phone', 'number']:
                # Mascarar números de telefone
                if isinstance(value, str) and len(value) >= 8:
                    masked[key] = f"{value[:2]}****{value[-2:]}"
                else:
                    masked[key] = "****"
            elif key_lower == 'email':
                # Mascarar email
                if isinstance(value, str) and '@' in value:
                    parts = value.split('@')
                    if len(parts[0]) > 2:
                        masked[key] = f"{parts[0][0]}****@{parts[1]}"
                    else:
                        masked[key] = "****@" + parts[1]
                else:
                    masked[key] = "****"
            else:
                # Recursão para objetos aninhados
                masked[key] = mask_sensitive_data(value, max_depth - 1)
        
        return masked
    
    elif isinstance(data, list):
        return [mask_sensitive_data(item, max_depth - 1) for item in data[:10]]  # Limitar tamanho
    
    elif isinstance(data, str):
        # Mascarar strings que parecem tokens
        if len(data) > 30 and re.match(r'^[a-zA-Z0-9+/=]+$', data):
            return f"{data[:8]}****{data[-8:]}"
        
        # Mascarar números que parecem telefones
        digits_only = re.sub(r'\D', '', data)
        if len(digits_only) >= 10:
            return f"{digits_only[:2]}****{digits_only[-2:]}"
        
        return data
    
    else:
        return data


def log_webhook_safely(payload: Dict[str, Any], logger_instance: logging.Logger, 
                      level: int = logging.INFO) -> None:
    """
    Faz log seguro de webhook payload mascarando dados sensíveis.
    
    Args:
        payload: Payload do webhook
        logger_instance: Instância do logger
        level: Nível do log
    """
    try:
        # Mascarar dados sensíveis
        safe_payload = mask_sensitive_data(payload, max_depth=3)
        
        # Limitar tamanho do JSON para logs
        json_str = json.dumps(safe_payload, ensure_ascii=False, separators=(',', ':'))
        if len(json_str) > 2000:
            json_str = json_str[:2000] + "...[truncated]"
        
        logger_instance.log(level, f"Webhook payload (masked): {json_str}")
        
    except Exception as e:
        logger_instance.error(f"Erro ao fazer log seguro do webhook: {e}")


def create_secure_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Cria logger com formatação segura.
    
    Args:
        name: Nome do logger
        level: Nível de log
        
    Returns:
        Logger configurado com formatação segura
    """
    logger_instance = logging.getLogger(name)
    
    if not logger_instance.handlers:
        handler = logging.StreamHandler()
        formatter = SecureFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s - %(message)s | %(req_id)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger_instance.addHandler(handler)
        logger_instance.setLevel(level)
    
    return logger_instance
