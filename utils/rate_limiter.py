"""
Sistema de rate limiting robusto e persistente
"""
import time
import sqlite3
import threading
import logging
from typing import Dict, Optional, Tuple
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DatabaseRateLimiter:
    """Rate limiter persistente usando SQLite."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_table()
    
    def _init_table(self):
        """Inicializa tabela de rate limiting."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rate_limits (
                    identifier TEXT PRIMARY KEY,
                    request_count INTEGER DEFAULT 1,
                    window_start REAL,
                    last_request REAL,
                    blocked_until REAL DEFAULT 0,
                    total_requests INTEGER DEFAULT 1,
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                )
            """)
            
            # Index para limpeza eficiente
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rate_limits_window 
                ON rate_limits(window_start)
            """)
            
            # Index para bloqueios
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rate_limits_blocked 
                ON rate_limits(blocked_until)
            """)
    
    @contextmanager
    def _get_connection(self):
        """Context manager para conexões SQLite."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")  # Melhor concorrência
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def is_allowed(self, identifier: str, max_requests: int = 10, 
                  window_seconds: int = 60, block_duration: int = 300) -> Tuple[bool, Dict]:
        """
        Verifica se requisição é permitida usando sliding window.
        
        Args:
            identifier: Identificador único (ex: número WhatsApp)
            max_requests: Máximo de requests por janela
            window_seconds: Tamanho da janela em segundos
            block_duration: Duração do bloqueio em segundos após limite excedido
            
        Returns:
            Tuple[bool, dict]: (permitido, info_debug)
        """
        with self.lock:
            now = time.time()
            window_start = now - window_seconds
            
            with self._get_connection() as conn:
                # Verificar se está bloqueado
                cursor = conn.execute(
                    "SELECT blocked_until FROM rate_limits WHERE identifier = ?",
                    (identifier,)
                )
                row = cursor.fetchone()
                
                if row and row[0] > now:
                    remaining_block = int(row[0] - now)
                    return False, {
                        "reason": "blocked",
                        "remaining_seconds": remaining_block,
                        "requests_in_window": max_requests
                    }
                
                # Contar requests na janela atual
                cursor = conn.execute("""
                    SELECT request_count, window_start, total_requests
                    FROM rate_limits 
                    WHERE identifier = ? AND window_start > ?
                """, (identifier, window_start))
                
                row = cursor.fetchone()
                
                if row:
                    current_count, old_window_start, total_requests = row
                    
                    # Se janela ainda é válida
                    if old_window_start > window_start:
                        if current_count >= max_requests:
                            # Bloquear usuário
                            blocked_until = now + block_duration
                            conn.execute("""
                                UPDATE rate_limits 
                                SET blocked_until = ?, last_request = ?
                                WHERE identifier = ?
                            """, (blocked_until, now, identifier))
                            
                            logger.warning(f"Rate limit exceeded for {identifier}, blocked for {block_duration}s")
                            return False, {
                                "reason": "rate_limited",
                                "requests_in_window": current_count,
                                "max_requests": max_requests,
                                "blocked_until": blocked_until
                            }
                        
                        # Incrementar contador
                        conn.execute("""
                            UPDATE rate_limits 
                            SET request_count = request_count + 1, 
                                last_request = ?,
                                total_requests = total_requests + 1
                            WHERE identifier = ?
                        """, (now, identifier))
                        
                        return True, {
                            "requests_in_window": current_count + 1,
                            "max_requests": max_requests,
                            "window_remaining": int(old_window_start + window_seconds - now)
                        }
                
                # Nova janela ou primeiro request
                conn.execute("""
                    INSERT OR REPLACE INTO rate_limits 
                    (identifier, request_count, window_start, last_request, blocked_until, total_requests)
                    VALUES (?, 1, ?, ?, 0, COALESCE((SELECT total_requests FROM rate_limits WHERE identifier = ?), 0) + 1)
                """, (identifier, now, now, identifier))
                
                return True, {
                    "requests_in_window": 1,
                    "max_requests": max_requests,
                    "window_remaining": window_seconds
                }
    
    def get_stats(self, identifier: str) -> Optional[Dict]:
        """Obtém estatísticas de um identificador."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT request_count, window_start, last_request, 
                       blocked_until, total_requests, created_at
                FROM rate_limits 
                WHERE identifier = ?
            """, (identifier,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            now = time.time()
            return {
                "requests_in_current_window": row[0],
                "window_start": row[1],
                "last_request": row[2],
                "blocked_until": row[3],
                "is_currently_blocked": row[3] > now,
                "total_requests": row[4],
                "first_seen": row[5]
            }
    
    def cleanup_old_entries(self, older_than_hours: int = 24):
        """Remove entradas antigas para manter banco limpo."""
        cutoff = time.time() - (older_than_hours * 3600)
        
        with self._get_connection() as conn:
            cursor = conn.execute("""
                DELETE FROM rate_limits 
                WHERE last_request < ? AND blocked_until < ?
            """, (cutoff, time.time()))
            
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old rate limit entries")
    
    def unblock_identifier(self, identifier: str) -> bool:
        """Remove bloqueio de um identificador (para admin)."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                UPDATE rate_limits 
                SET blocked_until = 0 
                WHERE identifier = ? AND blocked_until > ?
            """, (identifier, time.time()))
            
            return cursor.rowcount > 0


class MemoryRateLimiter:
    """Rate limiter simples em memória para fallback."""
    
    def __init__(self):
        self.requests: Dict[str, list] = {}
        self.lock = threading.Lock()
    
    def is_allowed(self, identifier: str, max_requests: int = 10, 
                  window_seconds: int = 60) -> Tuple[bool, Dict]:
        """Implementação simples em memória."""
        with self.lock:
            now = time.time()
            cutoff = now - window_seconds
            
            # Limpar requests antigos
            if identifier in self.requests:
                self.requests[identifier] = [
                    req_time for req_time in self.requests[identifier] 
                    if req_time > cutoff
                ]
            else:
                self.requests[identifier] = []
            
            # Verificar limite
            current_count = len(self.requests[identifier])
            if current_count >= max_requests:
                return False, {
                    "reason": "rate_limited",
                    "requests_in_window": current_count,
                    "max_requests": max_requests
                }
            
            # Adicionar request atual
            self.requests[identifier].append(now)
            
            return True, {
                "requests_in_window": current_count + 1,
                "max_requests": max_requests
            }


def create_rate_limiter(db_path: str) -> DatabaseRateLimiter:
    """Cria instância do rate limiter."""
    try:
        return DatabaseRateLimiter(db_path)
    except Exception as e:
        logger.error(f"Erro ao criar DatabaseRateLimiter: {e}")
        logger.warning("Usando MemoryRateLimiter como fallback")
        return MemoryRateLimiter()
