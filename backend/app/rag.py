"""RAG: chunking dos documentos da rede municipal de saúde, ingestão idempotente no Qdrant e busca (SPEC RF01)."""

import logging
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import ollama
from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.config import Settings
from app.errors import DependencyUnavailable
from app.llm import make_embeddings
from app.models import RetrievedChunk

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SUPPORTED_SUFFIXES = {".md", ".txt"}
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
SECTION_SEPARATOR = " › "

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


# --------------------------------------------------------------------------- chunking


@dataclass(frozen=True)
class Chunk:
    section: str | None
    text: str


def split_sections(text: str) -> list[tuple[str | None, str]]:
    """Divide o Markdown por títulos; a seção é o caminho de títulos ("Exames › Coleta de sangue")."""
    sections: list[tuple[str | None, str]] = []
    path: list[str] = []
    body: list[str] = []

    def flush() -> None:
        content = "\n".join(body).strip()
        if content:
            sections.append((SECTION_SEPARATOR.join(path) or None, content))
        body.clear()

    for line in text.splitlines():
        match = _HEADING.match(line)
        if match:
            flush()
            level = len(match.group(1))
            path[:] = path[: level - 1] + [match.group(2)]
        else:
            body.append(line)
    flush()
    return sections


def _tail(text: str, size: int) -> str:
    """Últimos `size` caracteres, começando numa fronteira de palavra."""
    if len(text) <= size:
        return text
    tail = text[-size:]
    space = tail.find(" ")
    return tail[space + 1 :] if space != -1 else tail


def _split_long(text: str, size: int, overlap: int) -> list[str]:
    """Parte um parágrafo maior que `size` em janelas com sobreposição, sem cortar palavras."""
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            space = text.rfind(" ", start, end)
            end = space if space > start else end
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        next_start = max(end - overlap, start + 1)
        space = text.find(" ", next_start, end)
        start = space + 1 if space != -1 else next_start
    return [p for p in pieces if p]


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[Chunk]:
    """Chunks de até `size` caracteres, agrupando parágrafos da mesma seção, com `overlap` entre vizinhos."""
    chunks: list[Chunk] = []
    for section, body in split_sections(text):
        pieces: list[str] = []
        for paragraph in _PARAGRAPH_BREAK.split(body):
            paragraph = paragraph.strip()
            if paragraph:
                pieces.extend(_split_long(paragraph, size, overlap) if len(paragraph) > size else [paragraph])

        current = ""
        for piece in pieces:
            candidate = f"{current}\n\n{piece}" if current else piece
            if len(candidate) <= size:
                current = candidate
                continue
            chunks.append(Chunk(section, current))
            tail = _tail(current, overlap)
            current = f"{tail}\n\n{piece}" if len(tail) + len(piece) + 2 <= size else piece
        if current:
            chunks.append(Chunk(section, current))
    return chunks


def expected_chunks(data_dir: Path) -> int:
    """Quantos pontos os documentos de `data_dir` geram — só chunking, sem embeddings."""
    return sum(
        len(chunk_text(p.read_text(encoding="utf-8")))
        for p in data_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )


def point_id(source: str, chunk_index: int) -> str:
    """ID determinístico: reingerir o mesmo arquivo sobrescreve os mesmos pontos (AC-RF01-2)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}#{chunk_index}"))


def embedding_text(chunk: Chunk) -> str:
    return f"{chunk.section}\n{chunk.text}" if chunk.section else chunk.text


# --------------------------------------------------------------------------- Qdrant


@dataclass
class IngestReport:
    files: int = 0
    chunks: int = 0
    skipped: list[str] = field(default_factory=list)


_QDRANT_ERRORS = (ResponseHandlingException, UnexpectedResponse, httpx.HTTPError, ConnectionError, TimeoutError)
_EMBED_ERRORS = (httpx.HTTPError, ollama.ResponseError, ConnectionError, TimeoutError)


@contextmanager
def _unavailable(dependency: str, errors: tuple[type[BaseException], ...]) -> Iterator[None]:
    try:
        yield
    except errors as exc:
        raise DependencyUnavailable(dependency, type(exc).__name__) from exc


class VectorStore:
    """Coleção do Qdrant com os chunks dos documentos da rede municipal de saúde."""

    def __init__(self, client: QdrantClient, embeddings: Embeddings, collection: str) -> None:
        self.client = client
        self.embeddings = embeddings
        self.collection = collection

    @classmethod
    def from_settings(cls, settings: Settings) -> "VectorStore":
        client = QdrantClient(url=settings.qdrant_url, timeout=int(settings.llm_timeout_s), check_compatibility=False)
        return cls(client, make_embeddings(settings), settings.qdrant_collection)

    # -- leitura

    def ping(self) -> None:
        with _unavailable("qdrant", _QDRANT_ERRORS):
            self.client.get_collections()

    def count(self) -> int:
        with _unavailable("qdrant", _QDRANT_ERRORS):
            if not self.client.collection_exists(self.collection):
                return 0
            return self.client.count(self.collection, exact=True).count

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        with _unavailable("ollama", _EMBED_ERRORS):
            vector = self.embeddings.embed_query(query)
        with _unavailable("qdrant", _QDRANT_ERRORS):
            if not self.client.collection_exists(self.collection):
                return []
            points = self.client.query_points(
                self.collection, query=vector, limit=top_k, with_payload=True
            ).points
        return [
            RetrievedChunk(
                source=p.payload["source"],
                section=p.payload.get("section"),
                chunk_index=p.payload["chunk_index"],
                text=p.payload["text"],
                similarity=p.score,
            )
            for p in points
            if p.payload
        ]

    # -- escrita

    def _ensure_collection(self, dim: int) -> None:
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                self.collection, vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
            )

    def ingest_file(self, path: Path) -> int:
        """Reingere um arquivo: remove os chunks antigos dele e grava os novos. Retorna o nº de chunks."""
        chunks = chunk_text(path.read_text(encoding="utf-8"))
        if not chunks:
            return 0
        with _unavailable("ollama", _EMBED_ERRORS):
            vectors = self.embeddings.embed_documents([embedding_text(c) for c in chunks])
        points = [
            PointStruct(
                id=point_id(path.name, i),
                vector=vector,
                payload={"source": path.name, "section": c.section, "chunk_index": i, "text": c.text},
            )
            for i, (c, vector) in enumerate(zip(chunks, vectors, strict=True))
        ]
        with _unavailable("qdrant", _QDRANT_ERRORS):
            self._ensure_collection(len(vectors[0]))
            self.client.delete(
                self.collection,
                points_selector=FilterSelector(
                    filter=Filter(must=[FieldCondition(key="source", match=MatchValue(value=path.name))])
                ),
            )
            self.client.upsert(self.collection, points=points)
        return len(points)

    def ingest_dir(self, data_dir: Path = DATA_DIR) -> IngestReport:
        self.ping()  # falha cedo e com mensagem clara se o Qdrant estiver fora (AC-RF01-4)
        report = IngestReport()
        for path in sorted(p for p in data_dir.iterdir() if p.is_file()):
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                logger.warning("ingest_skipped", extra={"file": path.name, "reason": "formato não suportado"})
                report.skipped.append(path.name)
                continue
            n = self.ingest_file(path)
            if n == 0:
                logger.warning("ingest_skipped", extra={"file": path.name, "reason": "arquivo vazio"})
                report.skipped.append(path.name)
                continue
            report.files += 1
            report.chunks += n
        return report

    def ensure_ingested(self, data_dir: Path = DATA_DIR) -> IngestReport | None:
        """Ingere se faltarem pontos: coleção vazia ou documentos novos em `data/` (startup do backend, RF05/RF07)."""
        if self.count() >= expected_chunks(data_dir):
            return None
        return self.ingest_dir(data_dir)
