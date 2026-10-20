"""Fábricas de modelos (ADR-13): LLM no Ollama (padrão), Claude ou Gemini; embeddings sempre locais."""

from typing import Literal

import anthropic
import httpx
import ollama
from google.genai import errors as google_errors
from langchain_anthropic import ChatAnthropic
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama, OllamaEmbeddings
from pydantic import SecretStr

from app.config import Settings

GENERATE_MAX_TOKENS = 400
JUDGE_MAX_TOKENS = 120
# As APIs contam o raciocínio (thinking) no limite de saída: folga para não cortar a resposta.
API_GENERATE_MAX_TOKENS = 2048
API_JUDGE_MAX_TOKENS = 1024
API_MAX_RETRIES = 2
WARM_UP_TIMEOUT_S = 300  # carregar o modelo a frio em CPU leva ~95 s

Role = Literal["generate", "judge"]


class LLMConfigError(RuntimeError):
    """Configuração inválida do provedor (chave ausente ou recusada) — erro 500, não 503."""


# Falhas do provedor que viram 503 na API: conexão, timeout, limite de uso, sobrecarga, 5xx
LLM_ERRORS: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    ollama.ResponseError,
    ConnectionError,
    TimeoutError,
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
    anthropic.OverloadedError,
    google_errors.ServerError,
)
# Chave inválida, sem permissão ou modelo inexistente: problema de configuração
LLM_CONFIG_ERRORS: tuple[type[BaseException], ...] = (
    LLMConfigError,
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    anthropic.NotFoundError,
)


def classify_llm_error(exc: BaseException) -> Literal["unavailable", "config"] | None:
    if isinstance(exc, google_errors.ClientError):  # 4xx do Gemini: 429 é limite de uso; o resto é configuração
        return "unavailable" if exc.code == 429 else "config"
    if isinstance(exc, LLM_CONFIG_ERRORS):
        return "config"
    if isinstance(exc, LLM_ERRORS):
        return "unavailable"
    return None


def _require_key(key: SecretStr | None, variable: str, provider: str) -> SecretStr:
    if key is None:
        raise LLMConfigError(f"LLM_PROVIDER={provider} exige {variable} no .env")
    return key


def _make(settings: Settings, role: Role) -> BaseChatModel:
    judge = role == "judge"
    if settings.llm_provider == "anthropic":
        # Sem temperature: os modelos atuais do Claude a rejeitam; o determinismo vem do JSON validado.
        extra = {"output_config": {"effort": settings.anthropic_effort}} if settings.anthropic_effort else {}
        return ChatAnthropic(
            model=settings.llm_model,
            api_key=_require_key(settings.anthropic_api_key, "ANTHROPIC_API_KEY", "anthropic"),
            max_tokens=API_JUDGE_MAX_TOKENS if judge else API_GENERATE_MAX_TOKENS,
            timeout=settings.llm_timeout_s,
            max_retries=API_MAX_RETRIES,
            **extra,
        )
    if settings.llm_provider == "google":
        return ChatGoogleGenerativeAI(
            model=settings.llm_model,
            api_key=_require_key(settings.google_api_key, "GOOGLE_API_KEY", "google"),
            temperature=0 if judge else 0.1,
            max_output_tokens=API_JUDGE_MAX_TOKENS if judge else API_GENERATE_MAX_TOKENS,
            response_mime_type="application/json" if judge else None,
            timeout=settings.llm_timeout_s,
            max_retries=API_MAX_RETRIES,
        )
    return ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        temperature=0 if judge else 0.1,
        num_predict=JUDGE_MAX_TOKENS if judge else GENERATE_MAX_TOKENS,
        format="json" if judge else None,
        client_kwargs={"timeout": settings.llm_timeout_s},
    )


def make_chat_model(settings: Settings) -> BaseChatModel:
    """Modelo de geração de respostas (RAG) e de extração de argumentos das tools."""
    return _make(settings, "generate")


def make_judge_model(settings: Settings) -> BaseChatModel:
    """Modelo das decisões no modo local: JSON, determinístico e com saída curta (ADR-11)."""
    return _make(settings, "judge")


def make_embeddings(settings: Settings) -> Embeddings:
    return OllamaEmbeddings(
        model=settings.embed_model,
        base_url=settings.ollama_base_url,
        client_kwargs={"timeout": settings.llm_timeout_s},
    )


def warm_up(settings: Settings) -> None:
    """Carrega embeddings (e o LLM, se for local) no Ollama para a 1ª pergunta não pagar o carregamento a frio.

    Gera 1 token e 1 embedding: só carregar com keep_alive não traz os pesos para a memória de fato.
    """
    base = settings.ollama_base_url
    if settings.llm_provider == "ollama":
        httpx.post(
            f"{base}/api/generate",
            json={"model": settings.llm_model, "prompt": "ok", "keep_alive": -1, "options": {"num_predict": 1}},
            timeout=WARM_UP_TIMEOUT_S,
        ).raise_for_status()
    httpx.post(
        f"{base}/api/embed",
        json={"model": settings.embed_model, "input": "aquecimento", "keep_alive": -1},
        timeout=WARM_UP_TIMEOUT_S,
    ).raise_for_status()


def message_text(message: BaseMessage) -> str:
    """Texto da resposta, ignorando blocos que não são texto (ex.: thinking das APIs)."""
    return str(message.text).strip()
