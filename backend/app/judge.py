"""Decisões tomadas pelo LLM local (modo local): saída JSON curta, validada por Pydantic (SPEC RF02)."""

import json
import re
import unicodedata
from typing import TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

from app.llm import message_text
from app.models import RetrievedChunk
from app.prompts import SCORE_SYSTEM, score_user_prompt
from app.rag import SECTION_SEPARATOR

# Score ancorado em evidência (ADR-11)
EVIDENCE_MIN_OVERLAP = 0.7
MIN_SCORE_WITH_EVIDENCE = 3
MAX_SCORE_WITHOUT_EVIDENCE = 2
FAIL_SAFE_SCORE = 1
TERM_PREFIX = 5
STOPWORDS = frozenset(
    "qual quais como onde quando quanto quanta quem porque preciso precisa precisam posso pode podem "
    "tenho temos fazer voces voce para pela pelo pelos sobre esta estao essa esse isso isto aqui "
    "existe existem minha meus minhas queria quero gostaria saber favor obrigado obrigada ainda "
    "tambem entao alguma algum mais muito".split()
)

V = TypeVar("V", bound=BaseModel)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class ScoreVerdict(BaseModel):
    evidencia: str = ""
    score: int = Field(ge=1, le=5)


def parse_verdict(text: str, model: type[V]) -> V | None:
    """JSON da resposta validado contra `model`; None se inválido ou fora do domínio."""
    match = _JSON_OBJECT.search(text)
    if not match:
        return None
    try:
        return model.model_validate(json.loads(match.group(0)))
    except (json.JSONDecodeError, ValidationError):
        return None


def normalize(text: str) -> str:
    """Minúsculas e sem acentos — base das comparações determinísticas."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", normalize(text))


def _overlap(evidence_words: list[str], text: str) -> float:
    context = set(_words(text))
    return sum(w in context for w in evidence_words) / len(evidence_words)


def evidence_source(evidence: str, chunks: list[RetrievedChunk]) -> RetrievedChunk | None:
    """Chunk de onde a citação saiu (≥ 70% das palavras presentes); None se "nenhuma" ou inexistente."""
    words = _words(evidence)
    if not words or not chunks or normalize(evidence).strip(" .") == "nenhuma":
        return None
    best = max(chunks, key=lambda c: _overlap(words, c.text))
    return best if _overlap(words, best.text) >= EVIDENCE_MIN_OVERLAP else None


def evidence_found(evidence: str, chunks: list[RetrievedChunk]) -> bool:
    return evidence_source(evidence, chunks) is not None


def _content_terms(text: str) -> set[str]:
    """Termos de conteúdo (4+ letras, fora das palavras vazias), reduzidos a um radical de 5 letras."""
    return {w[:TERM_PREFIX] for w in _words(text) if len(w) >= 4 and w not in STOPWORDS}


def evidence_on_topic(question: str, evidence: str, section: str | None = None) -> bool:
    """A citação (ou o título da seção dela) fala do que foi perguntado? Barra frases reais de outro assunto.

    Só o último título conta: o primeiro é o nome do documento e casaria com quase qualquer pergunta.
    """
    title = section.split(SECTION_SEPARATOR)[-1] if section else ""
    return bool(_content_terms(question) & _content_terms(f"{evidence} {title}"))


def anchored_score(verdict: ScoreVerdict, chunks: list[RetrievedChunk], question: str) -> int:
    source = evidence_source(verdict.evidencia, chunks)
    if source and evidence_on_topic(question, verdict.evidencia, source.section):
        return max(verdict.score, MIN_SCORE_WITH_EVIDENCE)
    return min(verdict.score, MAX_SCORE_WITHOUT_EVIDENCE)


class LLMJudge:
    """Modo local: cada decisão devolve (resultado, nº de chamadas ao LLM)."""

    def __init__(self, model: BaseChatModel) -> None:
        self.model = model

    def _ask(self, system: str, user: str) -> str:
        return message_text(self.model.invoke([SystemMessage(system), HumanMessage(user)]))

    def score(self, question: str, chunks: list[RetrievedChunk]) -> tuple[int, int]:
        """Relevância 1–5 do contexto. Saída inválida → 1 (falha segura)."""
        verdict = parse_verdict(self._ask(SCORE_SYSTEM, score_user_prompt(question, chunks)), ScoreVerdict)
        if verdict is None:
            return FAIL_SAFE_SCORE, 1
        return anchored_score(verdict, chunks, question), 1
