"""Configuração da aplicação, lida do ambiente / arquivo .env (SPEC RF05)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["ollama", "anthropic", "google"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM (ADR-13): local por padrão; Claude ou Gemini via API são opcionais
    llm_provider: LLMProvider = "ollama"
    llm_model: str = "llama3.2:3b"
    llm_timeout_s: float = Field(default=120, gt=0)
    anthropic_api_key: SecretStr | None = None
    anthropic_effort: str | None = None
    google_api_key: SecretStr | None = None

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

    @field_validator("anthropic_api_key", "google_api_key", "anthropic_effort", mode="before")
    @classmethod
    def _empty_as_none(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
