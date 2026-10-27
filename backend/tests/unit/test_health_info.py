"""Informações gerais de saúde do Ministério da Saúde (RF07, T-28)."""

import re
from pathlib import Path
from typing import Any

import pytest

from app.graph import GraphDeps, build_graph
from app.judge import LLMJudge
from app.models import RetrievedChunk
from app.prompts import HEALTH_INFO_NOTICE, HEALTH_INFO_PREFIX, with_health_notice
from app.rag import DATA_DIR
from app.text import normalize
from tests.fakes import FakeChatModel, FakeRetriever, chunk, scripted_judge

HEALTH_DOCS = sorted(DATA_DIR.glob(f"{HEALTH_INFO_PREFIX}*.md"))
# Os documentos não citam medicamentos nem doses: o assistente não indica remédio (RF07, regra 1).
MEDICAMENTOS = (
    "paracetamol", "dipirona", "ibuprofeno", "oseltamivir", "acido acetilsalicilico", "aas",
    "losartana", "captopril", "metformina", "amoxicilina", "mg",
)

DENGUE = chunk(
    "Sintomas da dengue: febre alta e repentina, dor de cabeça e dor atrás dos olhos.",
    source="saude-dengue.md",
    section="Sintomas da dengue",
)
UBS = chunk("A UBS funciona das 7h às 19h.", source="funcionamento.md", section="Horário de atendimento")


def test_os_quatro_documentos_de_saude_existem() -> None:
    assert [p.name for p in HEALTH_DOCS] == [
        "saude-dengue.md", "saude-diabetes.md", "saude-gripe.md", "saude-hipertensao.md",
    ]


@pytest.mark.parametrize("path", HEALTH_DOCS, ids=lambda p: p.name)
def test_documento_cita_a_fonte_oficial_e_nao_indica_remedio(path: Path) -> None:  # AC-RF07-1
    text = path.read_text(encoding="utf-8")
    assert re.search(r"https://www\.gov\.br/saude/\S+", text)
    assert "Não substitui avaliação profissional" in text
    normalized = normalize(text)
    for nome in MEDICAMENTOS:
        assert not re.search(rf"\b{nome}\b", normalized), nome


def test_aviso_so_quando_ha_trecho_de_saude() -> None:  # AC-RF07-5
    assert with_health_notice("Resposta.", [UBS, DENGUE]) == f"Resposta.\n\n{HEALTH_INFO_NOTICE}"
    assert with_health_notice("Resposta.", [UBS]) == "Resposta."
    assert with_health_notice("Resposta.", []) == "Resposta."


def run(contexts: list[RetrievedChunk], score: str, message: str) -> dict[str, Any]:
    deps = GraphDeps(
        retriever=FakeRetriever(contexts),
        chat_model=FakeChatModel(responses=["A dengue costuma começar com febre alta e repentina."]),
        judge=LLMJudge(FakeChatModel(responses=[scripted_judge("CONSULTA_RAG", score=score)] * 3)),
    )
    return build_graph(deps).invoke({"request_id": "t", "message": message, "history": [], "llm_calls": 0})


def test_resposta_com_documento_de_saude_termina_com_o_aviso() -> None:  # AC-RF07-2 (modelos simulados)
    evidencia = '{"evidencia": "Sintomas da dengue: febre alta e repentina, dor de cabeça e dor atrás dos olhos.", "score": 5}'
    state = run([DENGUE], evidencia, "Quais são os sintomas da dengue?")
    assert state["route"] == "CONSULTA_RAG" and state["fallback"] is False
    assert state["reply"].endswith(HEALTH_INFO_NOTICE)


def test_resposta_so_com_documento_da_ubs_nao_recebe_o_aviso() -> None:  # AC-RF07-5
    state = run([UBS], '{"evidencia": "A UBS funciona das 7h às 19h.", "score": 5}', "Que horas a UBS funciona?")
    assert state["fallback"] is False and HEALTH_INFO_NOTICE not in state["reply"]


def test_fallback_nao_recebe_o_aviso() -> None:  # AC-RF07-5
    state = run([DENGUE], '{"evidencia": "nenhuma", "score": 1}', "Quais são os sintomas da tuberculose?")
    assert state["fallback"] is True and HEALTH_INFO_NOTICE not in state["reply"]
