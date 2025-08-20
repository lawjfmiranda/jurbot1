import os
import json
import re
import logging
from typing import Optional, List

try:
    import google.generativeai as genai
except Exception:  # Library missing; we'll degrade gracefully
    genai = None  # type: ignore


logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_MODEL_QUALITY = os.getenv("GEMINI_MODEL_QUALITY", "gemini-1.5-pro")
FAQ_PATH = os.getenv("FAQ_PATH", os.path.join(os.path.dirname(__file__), "faq.json"))


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
    # Será sobrescrito por _load_allowed_areas() a partir do faq.json
    "Responsabilidade Civil",
    "Ação Penal",
    "Medida Protetiva",
    "Direito das Famílias",
    "Recursos",
    "FIES",
    "Flagrantes",
    "Inquérito policial",
]


def _strip_accents(text: str) -> str:
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')


_CACHED_ALLOWED: List[str] | None = None


def _load_allowed_areas() -> List[str]:
    global _CACHED_ALLOWED
    if _CACHED_ALLOWED is not None:
        return _CACHED_ALLOWED
    try:
        if os.path.exists(FAQ_PATH):
            with open(FAQ_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                areas = list((data.get("areas_atuacao") or {}).keys())
                if areas:
                    _CACHED_ALLOWED = areas
                    return areas
    except Exception:
        pass
    _CACHED_ALLOWED = ALLOWED_AREAS
    return _CACHED_ALLOWED


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
        "Responda APENAS com um JSON, sem texto extra, sem comentários, sem markdown.\n"
        "Formato: {\"intent\": <uma de %s>, \"area\": <opcional, uma de %s>, \"confidence\": <0..1>}\n"
        "Restrinja a área às opções listadas. Se não corresponder a nenhuma, deixe \"area\" vazia e use intent='desconhecido'.\n"
        "Texto do usuário: \n" % (ALLOWED_INTENTS, _load_allowed_areas())
    ) + user_text
    try:
        resp = model.generate_content(prompt)
        text = (resp.text or "").strip()
        import json as _json, re as _re
        try:
            data = _json.loads(text)
        except Exception:
            # Extrai o primeiro bloco que parece JSON
            m = _re.search(r"\{[\s\S]*\}", text)
            data = _json.loads(m.group(0)) if m else {}
        intent = data.get("intent")
        if intent not in ALLOWED_INTENTS:
            intent = "desconhecido"
        area = data.get("area") if area_in_allowed(data.get("area")) else None
        conf = float(data.get("confidence") or 0.5)
        logger.info("ai_service.extract_intent: parsed", extra={"intent": intent, "area": area, "confidence": conf})
        return {"intent": intent, "area": area, "confidence": conf}
    except Exception:
        logger.exception("ai_service.extract_intent: error in generation or parsing")
        # heurística como fallback final
        t = user_text.lower()
        if any(k in t for k in ["ajuda", "preciso", "duvida", "dúvida", "multa", "ipva", "preso", "policia", "carro", "transferir"]):
            return {"intent": "duvida_juridica", "confidence": 0.55}
        return {"intent": "desconhecido", "confidence": 0.3}


def area_in_allowed(area: Optional[str]) -> bool:
    if not area:
        return False
    return area in _load_allowed_areas()


def guess_area(user_text: str) -> Optional[str]:
    """Heurística para mapear texto a uma área permitida, com base nos nomes e sinônimos básicos."""
    text = _strip_accents(user_text.lower())
    for area in _load_allowed_areas():
        a = _strip_accents(area.lower())
        if a in text:
            return area
    # sinônimos
    synonyms = [
        ("Direito das Famílias", ["familia", "guarda", "pensao", "pensão", "divorcio", "divórcio"]),
        ("Ação Penal", ["crime", "criminal", "pena", "processo penal"]),
        ("Flagrantes", ["flagrante", "preso", "prisao", "prisão", "delegacia", "cadeia", "custodia", "custódia"]),
        ("Medida Protetiva", ["protetiva", "agressor", "violencia domestica", "violência doméstica"]),
        ("Responsabilidade Civil", ["indenizacao", "indenização", "dano moral", "acidente", "prejuizo", "prejuízo"]),
        ("Recursos", ["recurso", "apelar", "apelação", "agravo"]),
        ("FIES", ["fies", "financiamento estudantil"]),
        ("Inquérito policial", ["inquerito", "inquérito", "investigacao", "investigação"]),
    ]
    for area, keys in synonyms:
        for k in keys:
            if k in text:
                return area
    return None


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
    allowed = _load_allowed_areas()
    if not area_in_allowed(area):
        # tenta deduzir
        g = guess_area(question)
        area = g if g else allowed[0]
    areas_text = ", ".join(allowed)
    sys_prompt = (
        "Você é a JustIA da JM ADVOGADOS. Responda em pt-BR, de forma clara e empática. "
        f"Atue apenas nas áreas: {areas_text}. Se a pergunta não estiver dentro dessas áreas, responda brevemente que está fora do nosso escopo e ofereça ajuda nas áreas listadas. "
        "Traga visão geral, passos iniciais e cuidados. Não prometa resultados; não solicite documentos; evite citar artigos/leis. "
        "Comece sempre com: 'Isto é informativo e não substitui orientação de um advogado.' "
        f"Limite a {max_chars} caracteres.\n"
        f"Área foco: {area}.\n"
        "Pergunta: "
    )
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


