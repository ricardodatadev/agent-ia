"""Camadas determinísticas (zero tokens) e orquestração das decisões (SPEC RF02, ADR-07)."""

import logging
import re
from dataclasses import dataclass
from typing import Literal

from app.jev import classify_jev_error
from app.judge import Judge
from app.models import ChatTurn, GuardrailResult, Intent
from app.text import normalize

logger = logging.getLogger(__name__)

# Padrões de PII (Apêndice C.1), avaliados em ordem: o primeiro que casar define o tipo.
PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "cpf": re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)"),
    "cns": re.compile(r"(?<!\d)[1-9]\d{2}\s?\d{4}\s?\d{4}\s?\d{4}(?!\d)"),
    "rg": re.compile(r"(?<!\d)\d{1,2}\.\d{3}\.\d{3}-[\dxX](?!\w)"),
    "telefone": re.compile(r"(?<!\d)(?:\(?\d{2}\)?\s?)?9?\d{4}-?\d{4}(?!\d)"),
    # 11 dígitos com espaços, pontos ou traços: CPF ou telefone com espaços, dígito a dígito
    "numero_longo": re.compile(r"(?<!\d)(?:\d[\s.\-]?){10}\d(?!\d)"),
    "email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "email_extenso": re.compile(r"\b[\w.+-]+\s+arroba\s+[\w-]+(?:\s+ponto\s+[\w-]+)+", re.IGNORECASE),
}

# Termos de urgência normalizados (Apêndice C.2): casam como substring do texto sem acentos.
URGENCY_TERMS = (
    "dor no peito", "falta de ar", "nao consigo respirar", "dificuldade para respirar", "desmai",
    "sangramento", "sangrando muito", "convuls", "avc", "derrame", "infarto", "perdeu a consciencia",
    "nao acorda", "engasg", "envenen", "overdose", "suicid", "me matar",
)
SUICIDE_TERMS = ("suicid", "me matar")

# Trava de negação (Apêndice C.2): negador colado ao termo, com no máximo 4 palavras de ligação no meio.
# Qualquer outra palavra quebra a trava ("não estou com meus documentos e tenho uma dor no peito" é urgência).
_NEGATORS = r"(?:nao|nunca|nem|sem)"
_LINKING = r"(?:estou|esta|tenho|tem|tive|tinha|sinto|senti|sentindo|com|de|a|o|uma|um|nenhuma|nenhum|mais)"
_NEGATED_BEFORE = re.compile(rf"\b{_NEGATORS}\b(?:\s+{_LINKING}\b){{0,4}}\s*$")

UrgencySignal = Literal["urgent", "negated", "none"]


def urgency_signal(text: str) -> UrgencySignal:
    """`urgent`: a regra decide urgência; `negated`: só há termos negados (a regra se abstém); `none`."""
    normalized = normalize(text)
    found = False
    for term in URGENCY_TERMS:
        for match in re.finditer(re.escape(term), normalized):
            found = True
            if term.startswith("nao") or not _NEGATED_BEFORE.search(normalized[: match.start()]):
                return "urgent"
    return "negated" if found else "none"


def is_urgent(text: str) -> bool:
    return urgency_signal(text) == "urgent"


def mentions_suicide(text: str) -> bool:
    normalized = normalize(text)
    return any(term in normalized for term in SUICIDE_TERMS)


# Pergunta ambígua da rede (RF08, T-32): horário de "a UBS" ou "o posto" sem dizer qual unidade.
# "funciona" fica de fora: "como funciona o cadastro na UBS?" não é pergunta de horário.
_HOURS = re.compile(r"\b(?:horarios?|horas|abre|abrem|fecha|fecham|abert[oa]s?)\b")
_GENERIC_UNIT = re.compile(r"\b(?:ubs|posto|postinho|unidades?|centro de saude)\b")
_SPECIFIC_TERMS = (  # unidade, serviço ou exame citado: o RAG responde com o trecho certo
    "esperanca", "vila nova", "santa clara", "farmacia", "caps", "upa",
    "vacina", "exame", "coleta", "teste", "jejum", "dentista", "odonto", "consulta",
)
HISTORY_TURNS_FOR_UNIT = 4


def asks_network_hours(message: str, history: list[ChatTurn]) -> bool:
    """Pergunta de horário sem unidade, nem na mensagem nem nas últimas mensagens do cidadão."""
    text = normalize(message)
    if not (_HOURS.search(text) and _GENERIC_UNIT.search(text)):
        return False
    recent = normalize(" ".join(t.content for t in history[-HISTORY_TURNS_FOR_UNIT:] if t.role == "user"))
    return not any(term in f"{text} {recent}" for term in _SPECIFIC_TERMS)


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
    urgent: bool
    llm_calls: int


def check_input(message: str, judge: Judge) -> NoulDecision:
    """Noul: PII por regex → urgência → bloqueios semânticos (ADR-01, ADR-07 revisado na T-26).

    Quem decide a urgência depende do motor: o Jev responde a pergunta `urgencia` (e a regra de termos só
    entra como plano B se ele falhar); no modo local, a regra decide a urgência clara antes do LLM. Urgência
    passa à frente dos bloqueios semânticos: um bloqueio indevido deixaria o paciente sem orientação.
    """
    pii_type = find_pii(message)
    if pii_type:
        return NoulDecision(GuardrailResult(motivo="PII", camada="regex"), pii_type, urgent=False, llm_calls=0)
    if not judge.decides_urgency and is_urgent(message):
        return NoulDecision(None, None, urgent=True, llm_calls=0)
    try:
        result = judge.noul(message)
    except Exception as exc:
        if judge.decides_urgency and classify_jev_error(exc) is not None and is_urgent(message):
            # Plano B: o Jev falhou, mas a regra reconhece uma urgência — o atendimento segue sem ele.
            logger.warning("urgency_fallback", extra={"error": type(exc).__name__})
            return NoulDecision(None, None, urgent=True, llm_calls=0)
        raise
    urgent = result.urgent if result.urgent is not None else is_urgent(message)
    if urgent:
        return NoulDecision(None, None, urgent=True, llm_calls=result.calls)
    guardrail = GuardrailResult(motivo=result.motivo, camada=judge.layer) if result.motivo else None
    return NoulDecision(guardrail, None, urgent=False, llm_calls=result.calls)


@dataclass(frozen=True)
class IntentDecision:
    intent: Intent
    urgent: bool
    llm_calls: int


def classify_intent(message: str, history: list[ChatTurn], judge: Judge, urgent: bool = False) -> IntentDecision:
    """Urgência decidida no Noul chega pronta e vai direto ao atendimento humano, sem chamar o motor (ADR-07)."""
    if urgent:
        return IntentDecision("ATENDIMENTO_HUMANO", urgent=True, llm_calls=0)
    intent, calls = judge.choice(message, history)
    return IntentDecision(intent, urgent=False, llm_calls=calls)
