"""
Sistema de configuração centralizado com validação completa
"""
import os
import json
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    """Configurações do banco de dados."""
    path: str = field(default_factory=lambda: os.getenv("DB_PATH", "./advocacia.db"))
    timeout: float = 10.0
    enable_foreign_keys: bool = True


@dataclass
class EvolutionAPIConfig:
    """Configurações da Evolution API."""
    base_url: str = field(default_factory=lambda: os.getenv("EVOLUTION_API_BASE_URL", ""))
    instance_id: str = field(default_factory=lambda: os.getenv("EVOLUTION_INSTANCE_ID", ""))
    api_key: str = field(default_factory=lambda: os.getenv("EVOLUTION_API_KEY", ""))
    webhook_token: Optional[str] = field(default_factory=lambda: os.getenv("EVOLUTION_WEBHOOK_TOKEN"))
    
    def __post_init__(self):
        """Valida configurações obrigatórias."""
        missing = []
        if not self.base_url:
            missing.append("EVOLUTION_API_BASE_URL")
        if not self.instance_id:
            missing.append("EVOLUTION_INSTANCE_ID")
        if not self.api_key:
            missing.append("EVOLUTION_API_KEY")
        
        if missing:
            raise ValueError(f"Configurações Evolution API obrigatórias ausentes: {missing}")


@dataclass
class GoogleConfig:
    """Configurações do Google Calendar."""
    calendar_id: str = field(default_factory=lambda: os.getenv("GOOGLE_CALENDAR_ID", "primary"))
    service_account_json: str = field(default_factory=lambda: os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", ""))
    allow_attendees: bool = field(default_factory=lambda: os.getenv("CALENDAR_ALLOW_ATTENDEES", "0").strip() in ("1", "true", "True"))
    
    def __post_init__(self):
        """Valida service account JSON."""
        if not self.service_account_json:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON é obrigatório")
        
        # Validar se é JSON válido
        try:
            if self.service_account_json.strip().startswith("{"):
                json.loads(self.service_account_json)
            else:
                # Se não é JSON, assumir que é caminho para arquivo
                if not os.path.exists(self.service_account_json):
                    raise ValueError(f"Arquivo service account não encontrado: {self.service_account_json}")
        except json.JSONDecodeError:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON contém JSON inválido")


@dataclass
class GeminiConfig:
    """Configurações da IA Gemini."""
    api_key: Optional[str] = field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
    model_quality: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL_QUALITY", "gemini-1.5-pro"))
    enabled: bool = field(init=False)
    
    def __post_init__(self):
        """Define se IA está habilitada."""
        self.enabled = bool(self.api_key)
        if not self.enabled:
            logger.warning("Gemini API não configurada - funcionalidades de IA desabilitadas")


@dataclass
class RateLimitConfig:
    """Configurações de rate limiting."""
    max_requests_per_minute: int = field(default_factory=lambda: int(os.getenv("MAX_REQUESTS_PER_MINUTE", "20")))
    block_duration_seconds: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_BLOCK_DURATION", "300")))
    cleanup_interval_hours: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_CLEANUP_HOURS", "24")))
    min_interval_seconds: float = field(default_factory=lambda: float(os.getenv("MIN_MSG_INTERVAL", "0.5")))


@dataclass
class BusinessConfig:
    """Configurações de negócio."""
    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "America/Sao_Paulo"))
    business_start_hour: int = field(default_factory=lambda: int(os.getenv("BUSINESS_START_HOUR", "9")))
    business_end_hour: int = field(default_factory=lambda: int(os.getenv("BUSINESS_END_HOUR", "18")))
    admin_whatsapp: Optional[str] = field(default_factory=lambda: os.getenv("ADMIN_WHATSAPP"))
    
    def __post_init__(self):
        """Valida configurações de negócio."""
        if not (0 <= self.business_start_hour <= 23):
            raise ValueError("BUSINESS_START_HOUR deve estar entre 0 e 23")
        if not (0 <= self.business_end_hour <= 23):
            raise ValueError("BUSINESS_END_HOUR deve estar entre 0 e 23")
        if self.business_start_hour >= self.business_end_hour:
            raise ValueError("BUSINESS_START_HOUR deve ser menor que BUSINESS_END_HOUR")


@dataclass
class NotificationConfig:
    """Configurações de notificações."""
    internal_webhook_url: Optional[str] = field(default_factory=lambda: os.getenv("INTERNAL_WEBHOOK_URL"))
    smtp_host: Optional[str] = field(default_factory=lambda: os.getenv("SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_user: Optional[str] = field(default_factory=lambda: os.getenv("SMTP_USER"))
    smtp_pass: Optional[str] = field(default_factory=lambda: os.getenv("SMTP_PASS"))
    email_from: Optional[str] = field(default_factory=lambda: os.getenv("EMAIL_FROM"))
    email_to: Optional[str] = field(default_factory=lambda: os.getenv("EMAIL_TO"))
    
    def is_email_configured(self) -> bool:
        """Verifica se email está configurado."""
        return all([
            self.smtp_host, self.smtp_user, self.smtp_pass,
            self.email_from, self.email_to
        ])


@dataclass
class N8NConfig:
    """Configurações do n8n."""
    base_url: str = field(default_factory=lambda: os.getenv("N8N_BASE_URL", "http://localhost:5678"))
    enabled: bool = field(default_factory=lambda: os.getenv("N8N_ENABLED", "true").lower() == "true")
    
    def validate(self) -> List[str]:
        errors = []
        if self.enabled and not self.base_url:
            errors.append("N8N_BASE_URL é obrigatório quando n8n está habilitado")
        return errors

@dataclass
class SecurityConfig:
    """Configurações de segurança."""
    admin_token: Optional[str] = field(default_factory=lambda: os.getenv("ADMIN_TOKEN"))
    public_webhook_url: Optional[str] = field(default_factory=lambda: os.getenv("PUBLIC_WEBHOOK_URL"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    mask_sensitive_data: bool = field(default_factory=lambda: os.getenv("MASK_SENSITIVE_DATA", "1") in ("1", "true", "True"))
    
    def __post_init__(self):
        """Valida configurações de segurança."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level not in valid_levels:
            raise ValueError(f"LOG_LEVEL deve ser um de: {valid_levels}")


@dataclass
class AppConfig:
    """Configuração principal da aplicação."""
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    debug: bool = field(default_factory=lambda: os.getenv("FLASK_ENV") == "development")
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "production"))
    
    # Subconfigs
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    evolution: EvolutionAPIConfig = field(default_factory=EvolutionAPIConfig)
    google: GoogleConfig = field(default_factory=GoogleConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    n8n: N8NConfig = field(default_factory=N8NConfig)
    business: BusinessConfig = field(default_factory=BusinessConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    
    def validate(self) -> List[str]:
        """
        Valida toda a configuração.
        
        Returns:
            Lista de erros encontrados
        """
        errors = []
        
        # Validar porta
        if not (1 <= self.port <= 65535):
            errors.append("PORT deve estar entre 1 e 65535")
        
        # Validar subconfigs através de seus __post_init__
        try:
            self.evolution.__post_init__()
        except ValueError as e:
            errors.append(f"Evolution API: {e}")
        
        try:
            self.google.__post_init__()
        except ValueError as e:
            errors.append(f"Google Config: {e}")
        
        try:
            self.business.__post_init__()
        except ValueError as e:
            errors.append(f"Business Config: {e}")
        
        # Validar n8n
        errors.extend([f"n8n: {e}" for e in self.n8n.validate()])
        
        try:
            self.security.__post_init__()
        except ValueError as e:
            errors.append(f"Security Config: {e}")
        
        # Avisos (não são erros críticos)
        warnings = []
        
        if not self.security.admin_token:
            warnings.append("ADMIN_TOKEN não configurado - endpoints admin desabilitados")
        
        if not self.notification.is_email_configured() and not self.notification.internal_webhook_url:
            warnings.append("Nenhum sistema de notificação configurado")
        
        if not self.gemini.enabled:
            warnings.append("Gemini API não configurada - usando fallbacks heurísticos")
        
        # Log warnings
        for warning in warnings:
            logger.warning(f"Config Warning: {warning}")
        
        return errors
    
    def get_summary(self) -> Dict[str, Any]:
        """Retorna resumo da configuração (sem dados sensíveis)."""
        return {
            "app": {
                "port": self.port,
                "debug": self.debug,
                "environment": self.environment
            },
            "features": {
                "ai_enabled": self.gemini.enabled,
                "email_notifications": self.notification.is_email_configured(),
                "webhook_notifications": bool(self.notification.internal_webhook_url),
                "admin_endpoints": bool(self.security.admin_token),
                "rate_limiting": True,
                "secure_logging": self.security.mask_sensitive_data
            },
            "business": {
                "timezone": self.business.timezone,
                "business_hours": f"{self.business.business_start_hour}:00-{self.business.business_end_hour}:00",
                "admin_configured": bool(self.business.admin_whatsapp)
            },
            "apis": {
                "evolution_configured": bool(self.evolution.api_key),
                "google_calendar_configured": bool(self.google.service_account_json),
                "gemini_configured": self.gemini.enabled
            }
        }


def load_config() -> AppConfig:
    """
    Carrega e valida configuração completa.
    
    Returns:
        Configuração validada
        
    Raises:
        SystemExit: Se configuração inválida
    """
    try:
        config = AppConfig()
        errors = config.validate()
        
        if errors:
            logger.error("❌ Erros de configuração encontrados:")
            for error in errors:
                logger.error(f"  • {error}")
            
            logger.error("\n📝 Verifique as variáveis de ambiente no arquivo .env")
            logger.error("📚 Consulte README.md para configuração completa")
            
            raise SystemExit(1)
        
        logger.info("✅ Configuração carregada e validada com sucesso")
        
        # Log summary em debug
        if config.debug:
            summary = config.get_summary()
            logger.debug(f"Config Summary: {json.dumps(summary, indent=2, ensure_ascii=False)}")
        
        return config
        
    except Exception as e:
        logger.error(f"❌ Erro crítico ao carregar configuração: {e}")
        raise SystemExit(1)


# Instância global da configuração
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Obtém configuração global (lazy loading)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> AppConfig:
    """Recarrega configuração."""
    global _config
    _config = None
    return get_config()


# Para compatibilidade - funções que retornam valores específicos
def get_db_path() -> str:
    return get_config().database.path


def get_timezone() -> str:
    return get_config().business.timezone


def is_ai_enabled() -> bool:
    return get_config().gemini.enabled


def get_admin_whatsapp() -> Optional[str]:
    return get_config().business.admin_whatsapp
