"""Fábricas de modelos: chat de geração e embeddings (sempre locais, Ollama)."""

import httpx
import ollama
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_ollama import ChatOllama, OllamaEmbeddings

from app.config import Settings

GENERATE_MAX_TOKENS = 400
JUDGE_MAX_TOKENS = 120
WARM_UP_TIMEOUT_S = 300  # carregar o modelo a frio em CPU leva ~95 s

# Falhas do provedor do LLM que viram 503 na API (conexão, timeout, modelo ausente, 5xx)
LLM_ERRORS: tuple[type[BaseException], ...] = (httpx.HTTPError, ollama.ResponseError, ConnectionError, TimeoutError)


def make_chat_model(settings: Settings) -> BaseChatModel:
    """Modelo de geração de respostas (RAG) e de extração de argumentos das tools."""
    return ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        temperature=0.1,
        num_predict=GENERATE_MAX_TOKENS,
        client_kwargs={"timeout": settings.llm_timeout_s},
    )


def make_judge_model(settings: Settings) -> BaseChatModel:
    """Modelo das decisões no modo local: JSON, determinístico e com saída curta (ADR-11)."""
    return ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        temperature=0,
        num_predict=JUDGE_MAX_TOKENS,
        format="json",
        client_kwargs={"timeout": settings.llm_timeout_s},
    )


def make_embeddings(settings: Settings) -> Embeddings:
    return OllamaEmbeddings(
        model=settings.embed_model,
        base_url=settings.ollama_base_url,
        client_kwargs={"timeout": settings.llm_timeout_s},
    )


def warm_up(settings: Settings) -> None:
    """Carrega LLM e embeddings no Ollama para a 1ª pergunta não pagar o carregamento a frio.

    Gera 1 token e 1 embedding: só carregar com keep_alive não traz os pesos para a memória de fato.
    """
    base = settings.ollama_base_url
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
