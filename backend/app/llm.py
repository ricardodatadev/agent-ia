"""Fábricas de modelos: embeddings (sempre locais, Ollama)."""

from langchain_core.embeddings import Embeddings
from langchain_ollama import OllamaEmbeddings

from app.config import Settings


def make_embeddings(settings: Settings) -> Embeddings:
    return OllamaEmbeddings(
        model=settings.embed_model,
        base_url=settings.ollama_base_url,
        client_kwargs={"timeout": settings.llm_timeout_s},
    )
