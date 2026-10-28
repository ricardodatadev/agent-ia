"""Testes contra a stack real (Qdrant + Ollama com bge-m3). Rode com: pytest -m integration

Usa uma coleção própria, apagada no fim, para não interferir na `ubs_docs` do app.
"""

from collections.abc import Iterator

import httpx
import pytest

from app.config import Settings
from app.rag import DATA_DIR, VectorStore

pytestmark = pytest.mark.integration

TEST_COLLECTION = "ubs_docs_pytest"

# Regressão de recuperação (P02: bge-m3): pergunta → (arquivo, último título da seção) esperados no top-1
TOP1 = {
    "Preciso de jejum para exame de glicemia?": ("exames.md", "Preparo para exames de sangue"),
    "Qual o horário da vacina da gripe?": ("vacinas.md", "Campanha de vacinação contra a gripe (Influenza)"),
    "Quais documentos preciso levar na consulta?": ("funcionamento.md", "Documentos necessários para consulta"),
    "Como faço o teste do pezinho do meu bebê?": ("exames.md", "Teste do pezinho"),
    "Posso cancelar uma consulta marcada?": ("especialidades.md", "Faltas e cancelamentos"),
}
OUT_OF_SCOPE = ["Qual a capital da França?", "Me indica um filme de comédia", "Quem ganhou o jogo de futebol ontem?"]


@pytest.fixture(scope="module")
def store() -> Iterator[VectorStore]:
    settings = Settings(qdrant_collection=TEST_COLLECTION)
    vs = VectorStore.from_settings(settings)
    try:
        vs.ping()
        httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=5).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"Stack indisponível ({exc}). Suba com: docker compose up -d qdrant ollama ollama-pull")
    if vs.client.collection_exists(TEST_COLLECTION):
        vs.client.delete_collection(TEST_COLLECTION)
    vs.ingest_dir(DATA_DIR)
    yield vs
    vs.client.delete_collection(TEST_COLLECTION)


def test_reingestao_real_e_idempotente(store: VectorStore) -> None:  # AC-RF01-2
    before = store.count()
    report = store.ingest_dir(DATA_DIR)
    assert report.files == len(list(DATA_DIR.glob("*.md")))
    assert store.count() == before == report.chunks


@pytest.mark.parametrize(("question", "expected"), TOP1.items())
def test_top1_com_bge_m3(store: VectorStore, question: str, expected: tuple[str, str]) -> None:
    top = store.search(question, top_k=1)[0]
    assert (top.source, top.section.split(" › ")[-1] if top.section else None) == expected


def test_fora_do_nicho_tem_similaridade_menor_que_perguntas_cobertas(store: VectorStore) -> None:
    covered = min(store.search(q, top_k=1)[0].similarity for q in TOP1)
    off = max(store.search(q, top_k=1)[0].similarity for q in OUT_OF_SCOPE)
    assert off < covered, f"fora do nicho {off:.2f} >= coberta {covered:.2f}"


def test_api_no_ar_responde_health_e_bloqueio_por_regex() -> None:
    """Exige também o backend do compose em http://localhost:8000."""
    try:
        health = httpx.get("http://localhost:8000/health", timeout=10)
    except httpx.HTTPError as exc:
        pytest.fail(f"Backend indisponível ({exc}). Suba com: docker compose up -d")
    assert health.status_code == 200 and health.json()["collection_points"] > 0
    body = httpx.post("http://localhost:8000/chat", json={"message": "meu cpf é 123.456.789-09"}, timeout=30).json()
    assert body["route"] == "BLOQUEIO" and body["guardrail"] == {"motivo": "PII", "camada": "regex"}
