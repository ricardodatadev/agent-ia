"""Configuração da aplicação, lida do ambiente / arquivo .env (SPEC RF05)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    llm_model: str = "llama3.2:3b"
    llm_timeout_s: float = Field(default=120, gt=0)

    # Embeddings e busca (sempre locais)
    embed_model: str = "bge-m3"
    ollama_base_url: str = "http://localhost:11434"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "ubs_docs"
    top_k: int = Field(default=3, ge=1, le=10)
    score_threshold: int = Field(default=3, ge=1, le=5)
    auto_ingest: bool = True

    # API
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
