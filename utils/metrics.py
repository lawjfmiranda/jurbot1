"""
Sistema de métricas básicas para monitoramento
"""
import time
import threading
import json
from collections import defaultdict, deque
from functools import wraps
from typing import Dict, Any, Optional, List, Deque
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Coletor de métricas thread-safe."""
    
    def __init__(self, max_history: int = 1000):
        self.lock = threading.Lock()
        self.max_history = max_history
        
        # Contadores simples
        self.counters: Dict[str, int] = defaultdict(int)
        
        # Histórico de tempos de resposta (últimas N operações)
        self.response_times: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=max_history))
        
        # Timestamps de eventos para cálculos de rate
        self.events: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=max_history))
        
        # Última atualização de cada métrica
        self.last_updated: Dict[str, float] = {}
        
        # Início das métricas
        self.start_time = time.time()
        
        # Status de saúde dos serviços
        self.service_health: Dict[str, Dict[str, Any]] = {}
    
    def increment(self, metric: str, value: int = 1) -> None:
        """Incrementa contador."""
        with self.lock:
            self.counters[metric] += value
            self.last_updated[metric] = time.time()
    
    def record_time(self, metric: str, duration: float) -> None:
        """Registra tempo de resposta."""
        with self.lock:
            self.response_times[metric].append(duration)
            self.last_updated[metric] = time.time()
    
    def record_event(self, metric: str) -> None:
        """Registra evento com timestamp."""
        with self.lock:
            self.events[metric].append(time.time())
            self.last_updated[metric] = time.time()
    
    def set_service_health(self, service: str, status: str, details: Optional[Dict] = None) -> None:
        """Define status de saúde de um serviço."""
        with self.lock:
            self.service_health[service] = {
                "status": status,  # "healthy", "degraded", "unhealthy"
                "details": details or {},
                "last_check": time.time()
            }
    
    def get_counter(self, metric: str) -> int:
        """Obtém valor de contador."""
        with self.lock:
            return self.counters.get(metric, 0)
    
    def get_avg_response_time(self, metric: str, window_minutes: int = 5) -> Optional[float]:
        """Calcula tempo médio de resposta."""
        with self.lock:
            times = self.response_times.get(metric, deque())
            if not times:
                return None
            
            # Filtrar por janela de tempo se especificada
            if window_minutes > 0:
                cutoff = time.time() - (window_minutes * 60)
                recent_times = [t for t in times if t > cutoff]
                if not recent_times:
                    return None
                return sum(recent_times) / len(recent_times)
            
            return sum(times) / len(times)
    
    def get_rate_per_minute(self, metric: str, window_minutes: int = 5) -> float:
        """Calcula taxa de eventos por minuto."""
        with self.lock:
            events = self.events.get(metric, deque())
            if not events:
                return 0.0
            
            cutoff = time.time() - (window_minutes * 60)
            recent_events = [e for e in events if e > cutoff]
            
            if not recent_events:
                return 0.0
            
            time_span = max(time.time() - min(recent_events), 1)  # Evitar divisão por zero
            return (len(recent_events) / time_span) * 60
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Retorna resumo de todas as métricas."""
        with self.lock:
            uptime = time.time() - self.start_time
            
            summary = {
                "timestamp": datetime.now().isoformat(),
                "uptime_seconds": uptime,
                "uptime_human": self._format_duration(uptime),
                "counters": dict(self.counters),
                "rates": {},
                "response_times": {},
                "service_health": dict(self.service_health)
            }
            
            # Calcular rates e tempos de resposta
            for metric in self.events.keys():
                summary["rates"][f"{metric}_per_minute"] = self.get_rate_per_minute(metric)
            
            for metric in self.response_times.keys():
                avg_time = self.get_avg_response_time(metric)
                if avg_time is not None:
                    summary["response_times"][f"{metric}_avg_ms"] = round(avg_time * 1000, 2)
            
            return summary
    
    def _format_duration(self, seconds: float) -> str:
        """Formata duração em formato legível."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds/60:.1f}m"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours:.0f}h {minutes:.0f}m"
    
    def reset_metrics(self) -> None:
        """Reseta todas as métricas."""
        with self.lock:
            self.counters.clear()
            self.response_times.clear()
            self.events.clear()
            self.last_updated.clear()
            self.service_health.clear()
            self.start_time = time.time()
            logger.info("Métricas resetadas")


# Instância global
metrics = MetricsCollector()


def track_time(metric_name: str):
    """Decorator para medir tempo de execução."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                metrics.increment(f"{metric_name}_success")
                return result
            except Exception as e:
                metrics.increment(f"{metric_name}_error")
                raise
            finally:
                duration = time.time() - start_time
                metrics.record_time(metric_name, duration)
                metrics.record_event(metric_name)
        return wrapper
    return decorator


def track_counter(metric_name: str):
    """Decorator para contar execuções."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            metrics.increment(metric_name)
            metrics.record_event(metric_name)
            return func(*args, **kwargs)
        return wrapper
    return decorator


class HealthChecker:
    """Verificador de saúde dos serviços."""
    
    def __init__(self):
        self.checks: Dict[str, callable] = {}
    
    def register_check(self, service_name: str, check_func: callable) -> None:
        """Registra verificação de saúde para um serviço."""
        self.checks[service_name] = check_func
    
    def check_all_services(self) -> Dict[str, Dict[str, Any]]:
        """Executa todas as verificações de saúde."""
        results = {}
        
        for service, check_func in self.checks.items():
            try:
                start = time.time()
                result = check_func()
                duration = time.time() - start
                
                if isinstance(result, bool):
                    status = "healthy" if result else "unhealthy"
                    details = {"response_time_ms": round(duration * 1000, 2)}
                elif isinstance(result, dict):
                    status = result.get("status", "unknown")
                    details = result.get("details", {})
                    details["response_time_ms"] = round(duration * 1000, 2)
                else:
                    status = "unknown"
                    details = {"response": str(result)}
                
                results[service] = {
                    "status": status,
                    "details": details,
                    "last_check": time.time()
                }
                
                # Atualizar métricas globais
                metrics.set_service_health(service, status, details)
                
            except Exception as e:
                logger.exception(f"Erro ao verificar saúde do serviço {service}")
                status = "unhealthy"
                details = {"error": str(e)}
                
                results[service] = {
                    "status": status,
                    "details": details,
                    "last_check": time.time()
                }
                
                metrics.set_service_health(service, status, details)
        
        return results


# Instância global
health_checker = HealthChecker()


def check_database_health() -> Dict[str, Any]:
    """Verifica saúde do banco de dados."""
    try:
        import database
        with database.get_connection() as conn:
            cursor = conn.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "healthy", "details": {}}
    except Exception as e:
        return {"status": "unhealthy", "details": {"error": str(e)}}


def check_evolution_api_health() -> Dict[str, Any]:
    """Verifica saúde da Evolution API."""
    try:
        import whatsapp_service
        import requests
        import os
        
        # Fazer uma requisição simples para verificar conectividade
        base_url = os.getenv("EVOLUTION_API_BASE_URL")
        instance_id = os.getenv("EVOLUTION_INSTANCE_ID")
        api_key = os.getenv("EVOLUTION_API_KEY")
        
        if not all([base_url, instance_id, api_key]):
            return {"status": "degraded", "details": {"error": "Configuração incompleta"}}
        
        # Verificar status da instância (endpoint comum da Evolution API)
        url = f"{base_url.rstrip('/')}/instance/connectionState/{instance_id}"
        headers = {"apikey": api_key}
        
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        state = data.get("instance", {}).get("state", "unknown")
        
        if state == "open":
            return {"status": "healthy", "details": {"state": state}}
        else:
            return {"status": "degraded", "details": {"state": state}}
            
    except Exception as e:
        return {"status": "unhealthy", "details": {"error": str(e)}}


def check_google_calendar_health() -> Dict[str, Any]:
    """Verifica saúde do Google Calendar."""
    try:
        import calendar_service
        
        # Tentar obter serviço
        service = calendar_service._get_service()
        
        # Fazer uma requisição simples
        calendar_list = service.calendarList().list(maxResults=1).execute()
        
        return {"status": "healthy", "details": {"calendars_found": len(calendar_list.get("items", []))}}
        
    except Exception as e:
        return {"status": "unhealthy", "details": {"error": str(e)}}


def check_gemini_health() -> Dict[str, Any]:
    """Verifica saúde da API Gemini."""
    try:
        import ai_service
        import os
        
        if not os.getenv("GEMINI_API_KEY"):
            return {"status": "degraded", "details": {"error": "API key não configurada"}}
        
        # Fazer uma chamada simples
        response = ai_service._call_gemini_api("Test", temperature=0.1, max_tokens=10)
        
        if response:
            return {"status": "healthy", "details": {"response_length": len(response)}}
        else:
            return {"status": "degraded", "details": {"error": "Resposta vazia"}}
            
    except Exception as e:
        return {"status": "unhealthy", "details": {"error": str(e)}}


# Registrar verificações padrão
health_checker.register_check("database", check_database_health)
health_checker.register_check("evolution_api", check_evolution_api_health)
health_checker.register_check("google_calendar", check_google_calendar_health)
health_checker.register_check("gemini_ai", check_gemini_health)
