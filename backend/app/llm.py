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


def message_text(message: BaseMessage) -> str:
    """Texto da resposta, ignorando blocos que não são texto (ex.: thinking das APIs)."""
    return str(message.text).strip()
