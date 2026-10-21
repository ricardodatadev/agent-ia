"""Decisões Noul, Choice e Score pelo Jev da TypeSafe AI, via SDK oficial (SPEC RF06, ADR-14).

As perguntas ficam em `backend/jevs/*.json`, no formato da API, e são carregadas e validadas uma vez
na inicialização — com os modelos Pydantic do SDK e contra as rotas do grafo.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import ValidationError
from typesafe_sdk import (
    Choice,
    Noul,
    RetryPolicy,
    Score,
    SystemOneResponse,
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeAPIResponseValidationError,
    TypeSafeClient,
    TypeSafeInternalServerError,
    TypeSafeRateLimitError,
)

from app.config import Settings
from app.judge import DEFAULT_INTENT, FAIL_SAFE_SCORE, NoulResult, recent_history
from app.models import BlockReason, ChatTurn, GuardrailLayer, Intent, RetrievedChunk

logger = logging.getLogger(__name__)

# LGPD: em DEBUG o SDK registra o corpo das requisições (a mensagem do paciente). Travado em WARNING,
# mesmo com TYPESAFE_LOG_LEVEL=debug, porque este ajuste roda depois do import do SDK.
logging.getLogger("typesafe_sdk").setLevel(logging.WARNING)

JEVS_DIR = Path(__file__).resolve().parents[1] / "jevs"
NOUL_QUESTIONS: dict[str, BlockReason] = {"ofensa": "OFENSA", "pii": "PII"}
URGENCY_QUESTION = "urgencia"  # Noul na mesma requisição: não bloqueia, marca urgência
CHOICE_QUESTION = "intencao"
SCORE_QUESTION = "relevancia"
SCORE_LEVELS = 5  # níveis 0–4 → nota 1–5
RETRY_STATUSES = {408, 429, *range(500, 600)}


class JevConfigError(RuntimeError):
    """Configuração do Jev inválida (chave ausente, arquivo de perguntas divergente do grafo)."""


# --------------------------------------------------------------------------- perguntas


def _load_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise JevConfigError(f"Arquivo de perguntas do Jev não encontrado: {path}") from exc
    except json.JSONDecodeError as exc:
        raise JevConfigError(f"{path.name}: JSON inválido ({exc.msg}, linha {exc.lineno})") from exc
    if not isinstance(data, dict) or not data:
        raise JevConfigError(f"{path.name}: esperado um objeto {{nome: pergunta}}")
    return data


def _validate(path: Path, name: str, raw: Any, model: type[Noul] | type[Choice] | type[Score]) -> Any:
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors(include_url=False)[0]
        where = ".".join(str(p) for p in first["loc"]) or "(raiz)"
        raise JevConfigError(f"{path.name}: pergunta '{name}' inválida em '{where}': {first['msg']}") from exc


@dataclass(frozen=True)
class JevQuestions:
    noul: dict[str, Noul]
    choice: dict[str, Choice]
    score: dict[str, Score]

    @classmethod
    def load(cls, directory: Path = JEVS_DIR) -> "JevQuestions":
        """Carrega e valida os 3 arquivos; falha cedo, com mensagem clara, se divergirem do grafo."""
        noul_path, choice_path, score_path = (directory / f"{n}.json" for n in ("noul", "choice", "score"))
        noul_raw, choice_raw, score_raw = (_load_file(p) for p in (noul_path, choice_path, score_path))

        expected_noul = set(NOUL_QUESTIONS) | {URGENCY_QUESTION}
        if set(noul_raw) != expected_noul:
            raise JevConfigError(f"noul.json: esperadas as perguntas {sorted(expected_noul)}, encontradas {sorted(noul_raw)}")
        if set(choice_raw) != {CHOICE_QUESTION}:
            raise JevConfigError(f"choice.json: esperada só a pergunta '{CHOICE_QUESTION}', encontradas {sorted(choice_raw)}")
        if set(score_raw) != {SCORE_QUESTION}:
            raise JevConfigError(f"score.json: esperada só a pergunta '{SCORE_QUESTION}', encontradas {sorted(score_raw)}")

        noul = {n: _validate(noul_path, n, q, Noul) for n, q in noul_raw.items()}
        choice = {n: _validate(choice_path, n, q, Choice) for n, q in choice_raw.items()}
        score = {n: _validate(score_path, n, q, Score) for n, q in score_raw.items()}

        options, routes = set(choice[CHOICE_QUESTION].criteria), set(get_args(Intent))
        if options != routes:
            raise JevConfigError(
                f"choice.json: as opções de '{CHOICE_QUESTION}' devem ser as rotas do grafo {sorted(routes)}; "
                f"faltando {sorted(routes - options)}, sobrando {sorted(options - routes)}"
            )
        levels = len(score[SCORE_QUESTION].criteria)
        if levels != SCORE_LEVELS:
            raise JevConfigError(f"score.json: '{SCORE_QUESTION}' precisa de {SCORE_LEVELS} níveis (0–4), encontrados {levels}")
        return cls(noul=noul, choice=choice, score=score)


# --------------------------------------------------------------------------- erros


def classify_jev_error(exc: BaseException) -> Literal["unavailable", "config"] | None:
    """Indisponibilidade (conexão, timeout, 429, 5xx, resposta malformada) → 503; chave/perguntas → 500."""
    if isinstance(exc, JevConfigError):
        return "config"
    if isinstance(exc, (TypeSafeAPIConnectionError, TypeSafeRateLimitError, TypeSafeInternalServerError, TypeSafeAPIResponseValidationError)):
        return "unavailable"
    if isinstance(exc, TypeSafeAPIError):
        return "unavailable" if exc.status in RETRY_STATUSES else "config"
    return None


# --------------------------------------------------------------------------- juiz


def score_from_level(level: float) -> int:
    """Nível esperado do Jev (0–4, pode ser fracionário) → nota 1–5."""
    return max(1, min(SCORE_LEVELS, round(level) + 1))


class JevJudge:
    """Implementa `Judge` com o Jev; cada decisão é uma requisição ao `POST /v1/systemone`."""

    layer: GuardrailLayer = "jev"
    decides_urgency = True  # o Jev responde `urgencia`; a regra de termos só entra como plano B

    def __init__(
        self,
        client: TypeSafeClient,
        questions: JevQuestions,
        model: str,
        noul_threshold: float = 0.5,
        min_confidence: float = 0.5,
        urgency_threshold: float = 0.3,
    ) -> None:
        self.client = client
        self.questions = questions
        self.model = model
        self.noul_threshold = noul_threshold
        self.min_confidence = min_confidence
        self.urgency_threshold = urgency_threshold

    @classmethod
    def from_settings(cls, settings: Settings, questions: JevQuestions) -> "JevJudge":
        if settings.typesafe_api_key is None:
            raise JevConfigError("JEV_PROVIDER=typesafe exige TYPESAFE_API_KEY no .env")
        client = TypeSafeClient(
            api_key=settings.typesafe_api_key.get_secret_value(),
            model=settings.typesafe_model,
            timeout=settings.jev_timeout_s,
            retry=RetryPolicy(max_retries=2, http_statuses=set(RETRY_STATUSES), timeout=settings.jev_timeout_s * 3),
        )
        return cls(
            client,
            questions,
            settings.typesafe_model,
            settings.jev_noul_threshold,
            settings.jev_min_confidence,
            settings.jev_urgency_threshold,
        )

    def close(self) -> None:
        self.client.close()

    def _ask(self, decision: str, state: Any, questions: dict[str, Any]) -> SystemOneResponse:
        response = self.client.system_one(state=state, questions=questions, model=self.model)
        # LGPD: só metadados da decisão — nunca o state
        logger.info(
            "jev_answer",
            extra={
                "decision": decision,
                "jev_model": response.model,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "nouls": {n: round(a.noul, 3) for n, a in response.nouls.items()},
                "choices": {n: [a.choice, round(a.confidence, 3)] for n, a in response.choices.items()},
                "scores": {n: [round(a.score, 2), round(a.confidence, 3)] for n, a in response.scores.items()},
            },
        )
        return response

    def noul(self, message: str) -> NoulResult:
        """Ofensa, PII e urgência numa requisição.

        Bloqueia pelo maior valor de ofensa/PII ≥ limiar (resposta ausente → INDETERMINADO). A urgência é
        `urgencia` ≥ `JEV_URGENCY_THRESHOLD`; sem resposta para ela, devolve None e quem decide é a regra.
        """
        response = self._ask("noul", message, dict(self.questions.noul))
        urgency = response.nouls.get(URGENCY_QUESTION)
        urgent = None if urgency is None else urgency.noul >= self.urgency_threshold
        probs = {name: response.nouls.get(name) for name in NOUL_QUESTIONS}
        if any(answer is None for answer in probs.values()):
            return NoulResult("INDETERMINADO", urgent, 1)
        name, answer = max(probs.items(), key=lambda item: item[1].noul)  # type: ignore[union-attr]
        motivo = NOUL_QUESTIONS[name] if answer.noul >= self.noul_threshold else None  # type: ignore[union-attr]
        return NoulResult(motivo, urgent, 1)

    def choice(self, message: str, history: list[ChatTurn]) -> tuple[Intent, int]:
        """`state` estruturado com a mensagem atual e o histórico recente; opção fora das rotas → CONSULTA_RAG."""
        state = {
            "mensagem_atual": message,
            "historico": [
                {"autor": "paciente" if t.role == "user" else "assistente", "texto": t.content}
                for t in recent_history(history)
            ],
        }
        response = self._ask("choice", state, dict(self.questions.choice))
        answer = response.choices.get(CHOICE_QUESTION)
        if answer is None or answer.choice not in get_args(Intent):
            return DEFAULT_INTENT, 1
        return answer.choice, 1  # type: ignore[return-value]

    def score(self, question: str, chunks: list[RetrievedChunk]) -> tuple[int, int]:
        """Níveis 0–4 → nota 1–5; confiança abaixo do mínimo ou resposta ausente → nota 1 (fallback)."""
        state = {"pergunta": question, "trechos": [{"fonte": c.source, "texto": c.text} for c in chunks]}
        response = self._ask("score", state, dict(self.questions.score))
        answer = response.scores.get(SCORE_QUESTION)
        if answer is None or answer.confidence < self.min_confidence:
            return FAIL_SAFE_SCORE, 1
        return score_from_level(answer.score), 1


# --------------------------------------------------------------------------- escolha do motor


def resolve_engine(settings: Settings) -> Literal["typesafe", "llm"]:
    """`auto`: Jev se houver chave; senão, modo local. `typesafe` exige a chave (AC-RF06-1..3)."""
    if settings.jev_provider == "llm":
        return "llm"
    if settings.jev_provider == "typesafe":
        if settings.typesafe_api_key is None:
            raise JevConfigError("JEV_PROVIDER=typesafe exige TYPESAFE_API_KEY no .env")
        return "typesafe"
    return "typesafe" if settings.typesafe_api_key is not None else "llm"
