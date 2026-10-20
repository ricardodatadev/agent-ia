"""Dublês de teste: embeddings, LLM e retriever determinísticos, sem Ollama/Qdrant."""

import hashlib
import math
import re
import unicodedata
from collections.abc import Callable
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from app.models import RetrievedChunk


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


class FakeEmbeddings(Embeddings):
    """Bag-of-words com hashing: textos com palavras em comum ficam próximos no cosseno."""

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for word in re.findall(r"\w{3,}", _normalize(text)):
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]


Responder = Callable[[list[BaseMessage]], str | AIMessage]


class FakeChatModel(BaseChatModel):
    """LLM roteirizado: devolve as respostas na ordem (ou via função) e grava cada chamada."""

    responses: list[Any] = Field(default_factory=list)  # str | AIMessage | Responder
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError(f"Chamada inesperada ao LLM (#{len(self.calls)})")
        response = self.responses.pop(0)
        if callable(response):
            response = response(messages)
        message = response if isinstance(response, AIMessage) else AIMessage(content=response)
        return ChatResult(generations=[ChatGeneration(message=message)])


class FakeRetriever:
    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self.chunks = chunks or []
        self.queries: list[str] = []

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        self.queries.append(query)
        return self.chunks[:top_k]


def chunk(text: str, source: str = "exames.md", section: str | None = "Exames", index: int = 0) -> RetrievedChunk:
    return RetrievedChunk(source=source, section=section, chunk_index=index, text=text, similarity=0.8)


def scripted_judge(intencao: str = "CONSULTA_RAG", score: str = '{"evidencia": "nenhuma", "score": 1}') -> Responder:
    """Resposta do juiz conforme o prompt recebido (Choice ou Score) — independe da ordem das chamadas."""

    def respond(messages: list[BaseMessage]) -> str:
        system = str(messages[0].content)
        if "classifica a intenção" in system:
            return f'{{"intencao": "{intencao}"}}'
        return score

    return respond
