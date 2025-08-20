"""
Sistema de qualificação inteligente de leads por área jurídica
"""
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class LeadQualifier:
    """Sistema de qualificação de leads com perguntas específicas por área."""
    
    def __init__(self):
        self.qualification_flows = {
            "Responsabilidade Civil": {
                "questions": [
                    {
                        "id": "tipo_dano",
                        "question": "Qual tipo de dano você sofreu?",
                        "options": ["Danos materiais", "Danos morais", "Ambos", "Outro"],
                        "follow_up": "Pode me contar brevemente como aconteceu?"
                    },
                    {
                        "id": "valor_prejuizo",
                        "question": "Você consegue estimar o valor do prejuízo?",
                        "type": "valor",
                        "follow_up": "Tem alguma documentação que comprove este valor?"
                    },
                    {
                        "id": "responsavel",
                        "question": "Quem foi o responsável pelo dano?",
                        "options": ["Pessoa física", "Empresa", "Órgão público", "Não sei"],
                        "follow_up": "Esta pessoa/empresa tem patrimônio conhecido?"
                    },
                    {
                        "id": "prazo",
                        "question": "Quando aconteceu o fato?",
                        "type": "data",
                        "urgency_check": True,
                        "follow_up": "É importante agir rapidamente para não perder o prazo legal."
                    }
                ],
                "lead_score_weights": {
                    "valor_prejuizo": 3,
                    "responsavel": 2,
                    "prazo": 2,
                    "tipo_dano": 1
                }
            },
            
            "Direito das Famílias": {
                "questions": [
                    {
                        "id": "situacao_conjugal",
                        "question": "Qual sua situação atual?",
                        "options": ["Casado(a) - quer divórcio", "União estável - quer dissolução", 
                                  "Separado(a) - questões pendentes", "Solteiro(a) - questão de guarda/pensão"],
                        "follow_up": "Há quanto tempo estão juntos/separados?"
                    },
                    {
                        "id": "filhos",
                        "question": "Vocês têm filhos?",
                        "options": ["Sim, menores de idade", "Sim, maiores de idade", "Não"],
                        "conditional": {
                            "if": "Sim, menores de idade",
                            "then": "A guarda já está definida ou é uma questão a resolver?"
                        }
                    },
                    {
                        "id": "bens",
                        "question": "Há bens para dividir? (imóveis, veículos, empresas)",
                        "options": ["Sim, muitos bens", "Poucos bens", "Sem bens significativos"],
                        "follow_up": "Vocês fizeram pacto antenupcial ou união com regime específico?"
                    },
                    {
                        "id": "urgencia",
                        "question": "Há alguma situação de urgência?",
                        "options": ["Violência doméstica", "Pensão alimentícia atrasada", 
                                  "Mudança de cidade com criança", "Não há urgência"],
                        "urgency_check": True
                    }
                ],
                "lead_score_weights": {
                    "bens": 3,
                    "filhos": 2,
                    "urgencia": 2,
                    "situacao_conjugal": 1
                }
            },
            
            "Ação Penal": {
                "questions": [
                    {
                        "id": "situacao_processo",
                        "question": "Qual sua situação no processo?",
                        "options": ["Sou vítima", "Sou réu/investigado", "Sou testemunha", "Familiar do envolvido"],
                        "follow_up": "Em que fase está o processo atualmente?"
                    },
                    {
                        "id": "tipo_crime",
                        "question": "Qual o tipo de crime envolvido?",
                        "options": ["Crimes contra pessoa", "Crimes patrimoniais", 
                                  "Crimes de trânsito", "Outros crimes"],
                        "follow_up": "Pode me dar mais detalhes sobre o que aconteceu?"
                    },
                    {
                        "id": "fase_processo",
                        "question": "O processo está em que fase?",
                        "options": ["Inquérito policial", "Denúncia oferecida", 
                                  "Instrução", "Aguardando sentença", "Recurso"],
                        "urgency_check": True
                    },
                    {
                        "id": "preso",
                        "question": "A pessoa está presa?",
                        "options": ["Sim, prisão preventiva", "Sim, flagrante", 
                                  "Liberdade provisória", "Solto"],
                        "urgency_check": True,
                        "high_priority": ["Sim, prisão preventiva", "Sim, flagrante"]
                    }
                ],
                "lead_score_weights": {
                    "preso": 4,
                    "fase_processo": 3,
                    "tipo_crime": 2,
                    "situacao_processo": 1
                }
            },
            
            "Medida Protetiva": {
                "questions": [
                    {
                        "id": "situacao_violencia",
                        "question": "Qual a situação de violência?",
                        "options": ["Violência física", "Violência psicológica", 
                                  "Ameaças", "Violência patrimonial", "Múltiplas violências"],
                        "follow_up": "Está em situação de risco no momento?"
                    },
                    {
                        "id": "ja_registrou",
                        "question": "Já registrou boletim de ocorrência?",
                        "options": ["Sim, recentemente", "Sim, há tempo", "Não, mas quero registrar", "Não"],
                        "urgency_check": True
                    },
                    {
                        "id": "medida_existente",
                        "question": "Já tem alguma medida protetiva?",
                        "options": ["Sim, está valendo", "Sim, mas foi descumprida", 
                                  "Não, mas preciso", "Não sei"],
                        "high_priority": ["Sim, mas foi descumprida"]
                    },
                    {
                        "id": "risco_atual",
                        "question": "Como está sua segurança agora?",
                        "options": ["Em risco iminente", "Preocupada mas segura", 
                                  "Situação controlada", "Preciso sair de casa"],
                        "urgency_check": True,
                        "high_priority": ["Em risco iminente", "Preciso sair de casa"]
                    }
                ],
                "lead_score_weights": {
                    "risco_atual": 4,
                    "medida_existente": 3,
                    "situacao_violencia": 2,
                    "ja_registrou": 1
                }
            }
        }
    
    def get_questions_for_area(self, area: str) -> List[Dict]:
        """Retorna perguntas específicas para uma área."""
        return self.qualification_flows.get(area, {}).get("questions", [])
    
    def calculate_lead_score(self, area: str, answers: Dict[str, Any]) -> int:
        """Calcula score do lead baseado nas respostas."""
        if area not in self.qualification_flows:
            return 5  # Score médio para áreas não mapeadas
        
        weights = self.qualification_flows[area]["lead_score_weights"]
        score = 0
        max_score = 0
        
        for question_id, weight in weights.items():
            max_score += weight * 3  # Score máximo por pergunta
            answer = answers.get(question_id)
            
            if answer:
                # Score baseado no tipo de resposta
                if isinstance(answer, str):
                    if any(keyword in answer.lower() for keyword in 
                          ["sim", "muito", "grande", "alto", "urgente"]):
                        score += weight * 3
                    elif any(keyword in answer.lower() for keyword in 
                            ["médio", "razoável", "algum"]):
                        score += weight * 2
                    else:
                        score += weight * 1
                else:
                    score += weight * 2  # Score médio para outros tipos
        
        # Normalizar para 1-10
        if max_score > 0:
            return min(10, max(1, int((score / max_score) * 10)))
        return 5
    
    def check_urgency(self, area: str, answers: Dict[str, Any]) -> Dict[str, Any]:
        """Verifica se há situação de urgência."""
        urgency_info = {
            "is_urgent": False,
            "urgency_level": "normal",  # normal, high, critical
            "urgency_reasons": [],
            "recommended_action": ""
        }
        
        if area not in self.qualification_flows:
            return urgency_info
        
        questions = self.qualification_flows[area]["questions"]
        
        for question in questions:
            question_id = question["id"]
            answer = answers.get(question_id, "")
            
            # Verificar urgência por flag da pergunta
            if question.get("urgency_check") and answer:
                urgency_info["is_urgent"] = True
                urgency_info["urgency_reasons"].append(f"{question['question']}: {answer}")
            
            # Verificar respostas de alta prioridade
            if question.get("high_priority"):
                if answer in question["high_priority"]:
                    urgency_info["is_urgent"] = True
                    urgency_info["urgency_level"] = "critical"
                    urgency_info["urgency_reasons"].append(f"Situação crítica: {answer}")
        
        # Definir ação recomendada baseada na área e urgência
        if urgency_info["is_urgent"]:
            if area == "Medida Protetiva":
                urgency_info["recommended_action"] = "Agendamento prioritário - situação de risco"
            elif area == "Ação Penal" and urgency_info["urgency_level"] == "critical":
                urgency_info["recommended_action"] = "Contato imediato - pessoa presa"
            elif "prazo" in str(answers).lower():
                urgency_info["recommended_action"] = "Agendamento urgente - prazo legal"
            else:
                urgency_info["recommended_action"] = "Acompanhamento prioritário"
        
        return urgency_info
    
    def generate_summary(self, area: str, answers: Dict[str, Any]) -> str:
        """Gera resumo da qualificação para o advogado."""
        score = self.calculate_lead_score(area, answers)
        urgency = self.check_urgency(area, answers)
        
        summary_parts = [
            f"📋 **LEAD QUALIFICADO - {area.upper()}**",
            f"🎯 Score: {score}/10",
            f"⚡ Urgência: {urgency['urgency_level'].upper()}",
            "",
            "📝 **RESPOSTAS:**"
        ]
        
        # Adicionar respostas organizadas
        questions = self.get_questions_for_area(area)
        for question in questions:
            question_id = question["id"]
            answer = answers.get(question_id)
            if answer:
                summary_parts.append(f"• {question['question']}")
                summary_parts.append(f"  → {answer}")
        
        if urgency["is_urgent"]:
            summary_parts.extend([
                "",
                "🚨 **URGÊNCIA DETECTADA:**",
                f"• {urgency['recommended_action']}"
            ])
            
            for reason in urgency["urgency_reasons"]:
                summary_parts.append(f"• {reason}")
        
        return "\n".join(summary_parts)


# Instância global
lead_qualifier = LeadQualifier()
