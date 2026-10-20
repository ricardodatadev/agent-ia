"""Ingestão com Qdrant em memória e embeddings falsos (AC-RF01-1..4)."""

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.config import Settings
from app.errors import DependencyUnavailable
from app.graph import GraphDeps
from app.judge import LLMJudge
from app.main import create_app
from app.rag import DATA_DIR, VectorStore
from tests.fakes import FakeChatModel, FakeEmbeddings

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture
def store() -> VectorStore:
    return VectorStore(QdrantClient(":memory:"), FakeEmbeddings(), "ubs_docs_test")


def sources(store: VectorStore) -> set[str]:
    points, _ = store.client.scroll(store.collection, limit=1000, with_payload=True)
    return {p.payload["source"] for p in points if p.payload}


def test_ingere_ao_menos_um_ponto_por_arquivo(store: VectorStore) -> None:  # AC-RF01-1
    report = store.ingest_dir(DATA_DIR)
    files = {p.name for p in DATA_DIR.glob("*.md")}
    assert report.files == len(files)
    assert report.chunks == store.count() >= len(files)
    assert sources(store) == files


def test_payload_tem_campos_da_spec(store: VectorStore) -> None:
    store.ingest_dir(DATA_DIR)
    points, _ = store.client.scroll(store.collection, limit=1, with_payload=True)
    assert set(points[0].payload) == {"source", "section", "chunk_index", "text"}


def test_reingestao_e_idempotente(store: VectorStore) -> None:  # AC-RF01-2
    store.ingest_dir(DATA_DIR)
    first = store.count()
    store.ingest_dir(DATA_DIR)
    assert store.count() == first


def test_arquivo_menor_remove_chunks_antigos(store: VectorStore, tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text("# A\n\n" + "\n\n".join("texto " * 60 for _ in range(6)), encoding="utf-8")
    store.ingest_dir(tmp_path)
    assert store.count() > 1
    doc.write_text("# A\n\nCurto.", encoding="utf-8")
    store.ingest_dir(tmp_path)
    assert store.count() == 1


def test_ignora_vazio_e_formato_nao_suportado(store: VectorStore, tmp_path: Path) -> None:  # AC-RF01-3
    (tmp_path / "ok.md").write_text("# Ok\n\nHorário das 7h às 19h.", encoding="utf-8")
    (tmp_path / "vazio.md").write_text("", encoding="utf-8")
    (tmp_path / "manual.pdf").write_bytes(b"%PDF-1.4")
    report = store.ingest_dir(tmp_path)
    assert report.files == 1
    assert sorted(report.skipped) == ["manual.pdf", "vazio.md"]


def test_busca_retorna_chunk_relevante(store: VectorStore) -> None:
    store.ingest_dir(DATA_DIR)
    # Embeddings falsos casam palavras exatas; a qualidade semântica é verificada com bge-m3 real.
    results = store.search("glicemia de jejum", top_k=3)
    assert len(results) == 3
    assert results[0].source == "exames.md"
    assert results[0].similarity >= results[-1].similarity


def test_ensure_ingested_so_ingere_colecao_vazia(store: VectorStore) -> None:
    assert store.ensure_ingested(DATA_DIR) is not None
    assert store.ensure_ingested(DATA_DIR) is None


def test_qdrant_indisponivel_vira_erro_de_dependencia() -> None:
    store = VectorStore(QdrantClient(url="http://127.0.0.1:1", timeout=2, check_compatibility=False), FakeEmbeddings(), "x")
    with pytest.raises(DependencyUnavailable) as exc:
        store.ingest_dir(DATA_DIR)
    assert exc.value.dependency == "qdrant"


def test_cli_falha_com_mensagem_clara_sem_qdrant() -> None:  # AC-RF01-4
    proc = subprocess.run(
        [sys.executable, "scripts/ingest.py"],
        cwd=BACKEND_DIR,
        env={**os.environ, "QDRANT_URL": "http://127.0.0.1:1", "LLM_TIMEOUT_S": "2"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0
    assert "qdrant indisponível em http://127.0.0.1:1" in proc.stderr


def test_startup_ingere_colecao_vazia_e_pula_se_populada(caplog: pytest.LogCaptureFixture) -> None:
    store = VectorStore(QdrantClient(":memory:"), FakeEmbeddings(), "ubs_startup")
    deps = GraphDeps(retriever=store, chat_model=FakeChatModel(), judge=LLMJudge(FakeChatModel()))
    app = create_app(settings=Settings(auto_ingest=True), deps=deps, health_probe=lambda: {})
    with caplog.at_level(logging.INFO):
        with TestClient(app):
            pass
        assert store.count() > 0
        with TestClient(app):
            pass
    events = [r.getMessage() for r in caplog.records if r.getMessage().startswith("startup_ingest")]
    assert events == ["startup_ingest_done", "startup_ingest_skipped"]


def test_startup_com_qdrant_fora_nao_derruba_a_api(caplog: pytest.LogCaptureFixture) -> None:
    broken = VectorStore(QdrantClient(url="http://127.0.0.1:1", timeout=2, check_compatibility=False), FakeEmbeddings(), "x")
    deps = GraphDeps(retriever=broken, chat_model=FakeChatModel(), judge=LLMJudge(FakeChatModel()))
    with caplog.at_level(logging.INFO), TestClient(create_app(settings=Settings(auto_ingest=True), deps=deps, health_probe=lambda: {})) as client:
        assert client.get("/openapi.json").status_code == 200
    assert any(r.getMessage() == "startup_ingest_failed" for r in caplog.records)
