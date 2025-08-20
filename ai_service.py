import os
import logging
from typing import Optional

try:
    import google.generativeai as genai
except Exception:  # Library missing; we'll degrade gracefully
    genai = None  # type: ignore


logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_MODEL_QUALITY = os.getenv("GEMINI_MODEL_QUALITY", "gemini-1.5-pro")


def _ensure_client():
    if not GEMINI_API_KEY or not genai:
        logger.debug("ai_service: client unavailable (missing key or library)")
        return None
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        logger.debug("ai_service: configured generative model", extra={"model": GEMINI_MODEL})
        return genai.GenerativeModel(GEMINI_MODEL)
    except Exception:
        logger.exception("ai_service: failed to initialize client")
        return None


def _ensure_quality_client():
    if not GEMINI_API_KEY or not genai:
        logger.debug("ai_service: quality client unavailable (missing key or library)")
        return None
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        logger.debug("ai_service: configured quality model", extra={"model": GEMINI_MODEL_QUALITY})
        return genai.GenerativeModel(GEMINI_MODEL_QUALITY)
    except Exception:
        logger.exception("ai_service: failed to initialize quality client")
        return None


ALLOWED_INTENTS = [
    "saudacao",
    "duvida_juridica",
    "agendar",
    "cancelar",
    "remarcar",
    "ver_agendamentos",
    "areas",
    "informacoes",
    "desconhecido",
]

ALLOWED_AREAS = [
    "Direito de Família",
    "Direito do Trabalho",
]


def extract_intent(user_text: str) -> dict:
    """Classifica a intenção do usuário e, quando aplicável, sugere área.

    Retorno: { intent: one_of(ALLOWED_INTENTS), area: optional[str], confidence: float }
    """
    logger.info("ai_service.extract_intent: start")
    model = _ensure_client()
    if not model:
        # fallback heurístico simples
        t = user_text.lower()
        logger.warning("ai_service.extract_intent: fallback heuristics")
        if any(k in t for k in [
            "duvida", "dúvida", "ajuda", "caso", "processo", "problema", "orienta", "consulta",
            "multa", "carro", "veiculo", "veículo", "transferir", "ipva", "detran", "cnh",
            "guarda", "pensao", "pensão", "inventar", "inventário", "inventario"
        ]):
            return {"intent": "duvida_juridica", "confidence": 0.7}
        if any(k in t for k in ["cancelar", "desmarcar"]):
            return {"intent": "cancelar", "confidence": 0.8}
        if any(k in t for k in ["remarcar", "adiantar", "antecipar"]):
            return {"intent": "remarcar", "confidence": 0.8}
        if any(k in t for k in ["agendar", "consulta"]):
            return {"intent": "agendar", "confidence": 0.7}
        if any(k in t for k in ["horário", "endere", "funciona"]):
            return {"intent": "informacoes", "confidence": 0.6}
        if any(k in t for k in ["trabalho", "demiss", "rescis"]):
            return {"intent": "duvida_juridica", "area": "Direito do Trabalho", "confidence": 0.6}
        if any(k in t for k in ["família", "familia", "guarda", "pensão", "pensao", "divórcio", "divorcio"]):
            return {"intent": "duvida_juridica", "area": "Direito de Família", "confidence": 0.6}
        if any(k in t for k in ["oi", "ola", "olá", "bom dia", "boa tarde", "boa noite"]):
            return {"intent": "saudacao", "confidence": 0.6}
        return {"intent": "desconhecido", "confidence": 0.2}

    prompt = (
        "Você é um classificador de intenções para um chatbot jurídico em pt-BR. "
        "Retorne UM JSON com chaves: intent (uma de %s), area (opcional, uma de %s), confidence (0..1). "
        "Se fora do escopo jurídico, marque intent='desconhecido'. Texto: \n" % (ALLOWED_INTENTS, ALLOWED_AREAS)
    ) + user_text
    try:
        resp = model.generate_content(prompt)
        text = (resp.text or "").strip()
        import json as _json
        data = _json.loads(text)
        intent = data.get("intent")
        if intent not in ALLOWED_INTENTS:
            intent = "desconhecido"
        area = data.get("area") if area_in_allowed(data.get("area")) else None
        conf = float(data.get("confidence") or 0.5)
        logger.info("ai_service.extract_intent: parsed", extra={"intent": intent, "area": area, "confidence": conf})
        return {"intent": intent, "area": area, "confidence": conf}
    except Exception:
        logger.exception("ai_service.extract_intent: error in generation or parsing")
        return {"intent": "desconhecido", "confidence": 0.3}


def area_in_allowed(area: Optional[str]) -> bool:
    if not area:
        return False
    return area in ALLOWED_AREAS


def small_talk_reply(base_text: str, user_text: Optional[str] = None, max_chars: int = 280) -> str:
    """Reescreve base_text em tom mais humano/empático, mantendo o conteúdo e limites.

    Se a IA falhar, retorna base_text.
    """
    model = _ensure_client()
    if not model:
        logger.debug("ai_service.small_talk: fallback (no model)")
        return base_text
    sys_prompt = (
        "Reescreva a mensagem abaixo em pt-BR, mantendo o significado, tom profissional, acolhedor e claro. "
        f"Limite a {max_chars} caracteres. Não invente informações novas.\nMensagem:\n"
    )
    try:
        resp = model.generate_content(sys_prompt + base_text)
        text = (resp.text or "").strip()
        if len(text) > max_chars:
            text = text[:max_chars]
        logger.debug("ai_service.small_talk: success", extra={"len": len(text)})
        return text or base_text
    except Exception:
        logger.exception("ai_service.small_talk: error in generation")
        return base_text


def legal_answer(area: str, question: str, max_chars: int = 700) -> str:
    """Responde dúvidas jurídicas genéricas com disclaimers e limites. Não dá aconselhamento específico."""
    logger.info("ai_service.legal_answer: start", extra={"area": area})
    model = _ensure_quality_client() or _ensure_client()
    if not model:
        logger.warning("ai_service.legal_answer: fallback (no model)")
        return (
            "Isto é informativo e não substitui orientação de um advogado. "
            "Podemos conversar mais na consulta para analisar seu caso."
        )
    if not area_in_allowed(area):
        area = "Direito do Trabalho"
    sys_prompt = (
        "Você é a JustIA, assistente de um escritório de advocacia brasileiro. Responda em pt-BR. "
        "Atue apenas em %s. Traga visão geral, passos iniciais e direitos de forma clara. "
        "Não prometa resultados; não peça documentos; não cite artigos específicos. "
        "Sempre inicie com: 'Isto é informativo e não substitui orientação de um advogado.' "
        f"Limite a {max_chars} caracteres.\nPergunta: "
    ) % area
    try:
        resp = model.generate_content(sys_prompt + question)
        text = (resp.text or "").strip()
        if len(text) > max_chars:
            text = text[:max_chars]
        logger.info("ai_service.legal_answer: success", extra={"len": len(text)})
        return text
    except Exception:
        logger.exception("ai_service.legal_answer: error in generation")
        return (
            "Isto é informativo e não substitui orientação de um advogado. "
            "Posso te explicar melhor em uma consulta rápida."
        )


