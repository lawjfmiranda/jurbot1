"""
Sistema de validação e sanitização de inputs para segurança
"""
import re
import html
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def validate_whatsapp_number(number: str) -> bool:
    """
    Valida formato de número WhatsApp.
    
    Args:
        number: Número a ser validado
        
    Returns:
        True se válido, False caso contrário
    """
    if not number or not isinstance(number, str):
        return False
    
    # Remove todos os caracteres não numéricos
    cleaned = re.sub(r'\D', '', number)
    
    # Número deve ter entre 10 e 15 dígitos (padrão internacional)
    return 10 <= len(cleaned) <= 15


def validate_email(email: str) -> bool:
    """
    Valida formato de email.
    
    Args:
        email: Email a ser validado
        
    Returns:
        True se válido, False caso contrário
    """
    if not email or not isinstance(email, str):
        return False
    
    # Pattern RFC 5322 simplificado mas robusto
    pattern = r'^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
    
    return bool(re.match(pattern, email)) and len(email) <= 254


def sanitize_text(text: str, max_length: int = 1000) -> str:
    """
    Remove caracteres perigosos e limita tamanho do texto.
    
    Args:
        text: Texto a ser sanitizado
        max_length: Tamanho máximo permitido
        
    Returns:
        Texto sanitizado
    """
    if not text or not isinstance(text, str):
        return ""
    
    # Limitar tamanho
    if len(text) > max_length:
        text = text[:max_length]
    
    # Escapar HTML para prevenir XSS
    text = html.escape(text)
    
    # Remove caracteres de controle perigosos, mas mantém acentos e quebras de linha
    safe_chars = []
    for char in text:
        # Permitir: letras, números, pontuação comum, acentos, espaços, quebras de linha
        if (char.isprintable() or 
            char in '\n\r\t' or 
            char in 'áàãâéêíóôõúçÁÀÃÂÉÊÍÓÔÕÚÇñÑ'):
            safe_chars.append(char)
    
    result = ''.join(safe_chars).strip()
    
    # Log suspeitas de tentativas de injeção
    if len(result) != len(text.strip()):
        logger.warning(f"Caracteres suspeitos removidos do input. Original: {len(text)}, Sanitizado: {len(result)}")
    
    return result


def validate_name(name: str) -> bool:
    """
    Valida nome completo.
    
    Args:
        name: Nome a ser validado
        
    Returns:
        True se válido, False caso contrário
    """
    if not name or not isinstance(name, str):
        return False
    
    # Remove espaços extras
    name = name.strip()
    
    # Nome deve ter pelo menos 2 caracteres e no máximo 100
    if len(name) < 2 or len(name) > 100:
        return False
    
    # Deve conter pelo menos uma letra
    if not re.search(r'[a-zA-ZáàãâéêíóôõúçÁÀÃÂÉÊÍÓÔÕÚÇñÑ]', name):
        return False
    
    # Não deve conter caracteres especiais perigosos
    dangerous_chars = ['<', '>', '"', "'", '&', ';', '(', ')', '{', '}', '[', ']']
    if any(char in name for char in dangerous_chars):
        return False
    
    return True


def sanitize_search_query(query: str) -> str:
    """
    Sanitiza query de busca para prevenir SQL injection.
    
    Args:
        query: Query de busca
        
    Returns:
        Query sanitizada
    """
    if not query or not isinstance(query, str):
        return ""
    
    # Limitar tamanho
    query = query[:100]
    
    # Escapar caracteres especiais do SQL LIKE
    query = query.replace('\\', '\\\\')  # Escape primeiro
    query = query.replace('%', '\\%')
    query = query.replace('_', '\\_')
    query = query.replace('[', '\\[')
    query = query.replace(']', '\\]')
    
    # Remove caracteres de controle
    query = re.sub(r'[\x00-\x1f\x7f]', '', query)
    
    # Remove múltiplos espaços
    query = re.sub(r'\s+', ' ', query).strip()
    
    return query


def validate_webhook_payload(payload: Dict[str, Any]) -> bool:
    """
    Valida estrutura básica do payload do webhook.
    
    Args:
        payload: Payload do webhook
        
    Returns:
        True se estrutura válida, False caso contrário
    """
    if not isinstance(payload, dict):
        return False
    
    # Verificar se tem campos básicos esperados
    required_fields = ['event', 'instance']
    for field in required_fields:
        if field not in payload:
            logger.warning(f"Campo obrigatório '{field}' ausente no webhook payload")
            return False
    
    # Validar tipos básicos
    if not isinstance(payload.get('event'), str):
        return False
    
    if not isinstance(payload.get('instance'), str):
        return False
    
    return True


class InputValidator:
    """Classe utilitária para validação centralizada de inputs."""
    
    @staticmethod
    def validate_client_data(whatsapp_number: str, full_name: Optional[str] = None, 
                           email: Optional[str] = None) -> Dict[str, Any]:
        """
        Valida dados do cliente.
        
        Returns:
            Dict com 'valid': bool e 'errors': list
        """
        errors = []
        
        # Validar número WhatsApp
        if not validate_whatsapp_number(whatsapp_number):
            errors.append("Número de WhatsApp inválido")
        
        # Validar nome se fornecido
        if full_name is not None and not validate_name(full_name):
            errors.append("Nome inválido")
        
        # Validar email se fornecido
        if email is not None and email.strip() and not validate_email(email):
            errors.append("Email inválido")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    @staticmethod
    def sanitize_client_data(whatsapp_number: str, full_name: Optional[str] = None,
                           email: Optional[str] = None, case_summary: Optional[str] = None) -> Dict[str, Optional[str]]:
        """
        Sanitiza dados do cliente.
        
        Returns:
            Dict com dados sanitizados
        """
        return {
            'whatsapp_number': re.sub(r'\D', '', whatsapp_number) if whatsapp_number else "",
            'full_name': sanitize_text(full_name, 100) if full_name else None,
            'email': email.strip().lower() if email else None,
            'case_summary': sanitize_text(case_summary, 500) if case_summary else None
        }
