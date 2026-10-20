"""Camadas determinísticas (zero tokens) e orquestração das decisões (SPEC RF02, ADR-07)."""

import re
from dataclasses import dataclass

from app.judge import Judge
from app.models import ChatTurn, GuardrailResult, Intent
from app.text import normalize

# Padrões de PII (Apêndice C.1), avaliados em ordem: o primeiro que casar define o tipo.
PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "cpf": re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)"),
    "cns": re.compile(r"(?<!\d)[1-9]\d{2}\s?\d{4}\s?\d{4}\s?\d{4}(?!\d)"),
    "rg": re.compile(r"(?<!\d)\d{1,2}\.\d{3}\.\d{3}-[\dxX](?!\w)"),
    "telefone": re.compile(r"(?<!\d)(?:\(?\d{2}\)?\s?)?9?\d{4}-?\d{4}(?!\d)"),
    "email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
}

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


def find_pii(text: str) -> str | None:
    """Tipo do primeiro dado pessoal encontrado por regex, ou None."""
    for kind, pattern in PII_PATTERNS.items():
        if pattern.search(text):
            return kind
    return None


@dataclass(frozen=True)
class NoulDecision:
    guardrail: GuardrailResult | None
    pii_type: str | None
    llm_calls: int


def check_input(message: str, judge: Judge) -> NoulDecision:
    """Regex primeiro (zero tokens); só o que ela não pega vai para o motor de decisões (ADR-01).

    Urgência sem PII não passa pela camada semântica: um bloqueio indevido aqui deixaria o paciente
    sem orientação (ADR-07, revisão: o Noul-LLM bloqueava "se envenenou" e "me matar").
    """
    pii_type = find_pii(message)
    if pii_type:
        return NoulDecision(GuardrailResult(motivo="PII", camada="regex"), pii_type, llm_calls=0)
    if is_urgent(message):
        return NoulDecision(None, None, llm_calls=0)
    motivo, calls = judge.noul(message)
    guardrail = GuardrailResult(motivo=motivo, camada=judge.layer) if motivo else None
    return NoulDecision(guardrail, None, llm_calls=calls)


@dataclass(frozen=True)
class IntentDecision:
    intent: Intent
    urgent: bool
    llm_calls: int


def classify_intent(message: str, history: list[ChatTurn], judge: Judge) -> IntentDecision:
    """Urgência conhecida vai direto para atendimento humano, sem chamar o motor de decisões (ADR-07)."""
    if is_urgent(message):
        return IntentDecision("ATENDIMENTO_HUMANO", urgent=True, llm_calls=0)
    intent, calls = judge.choice(message, history)
    return IntentDecision(intent, urgent=False, llm_calls=calls)
