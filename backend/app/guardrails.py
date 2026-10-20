"""Camadas determinísticas (zero tokens) e orquestração das decisões (SPEC RF02, ADR-07)."""

from dataclasses import dataclass

from app.judge import LLMJudge
from app.models import ChatTurn, Intent
from app.text import normalize

# Termos de urgência normalizados (Apêndice C.2): casam como substring do texto sem acentos.
URGENCY_TERMS = (
    "dor no peito", "falta de ar", "nao consigo respirar", "dificuldade para respirar", "desmai",
    "sangramento", "sangrando muito", "convuls", "avc", "derrame", "infarto", "perdeu a consciencia",
    "nao acorda", "engasg", "envenen", "overdose", "suicid", "me matar",
)
SUICIDE_TERMS = ("suicid", "me matar")


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    normalized = normalize(text)
    return any(term in normalized for term in terms)


def is_urgent(text: str) -> bool:
    return _has_any(text, URGENCY_TERMS)


def mentions_suicide(text: str) -> bool:
    return _has_any(text, SUICIDE_TERMS)


@dataclass(frozen=True)
class IntentDecision:
    intent: Intent
    urgent: bool
    llm_calls: int


def classify_intent(message: str, history: list[ChatTurn], judge: LLMJudge) -> IntentDecision:
    """Urgência conhecida vai direto para atendimento humano, sem chamar o motor de decisões (ADR-07)."""
    if is_urgent(message):
        return IntentDecision("ATENDIMENTO_HUMANO", urgent=True, llm_calls=0)
    intent, calls = judge.choice(message, history)
    return IntentDecision(intent, urgent=False, llm_calls=calls)
