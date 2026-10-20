"""Noul no grafo: bloqueio por regex e pelo LLM, respostas fixas e logs sem PII (AC-RF02-1..5, RNF01)."""

import logging

import pytest

from app.graph import GraphDeps, build_graph
from app.judge import LLMJudge
from app.prompts import BLOCK_REPLIES
from tests.fakes import FakeChatModel, FakeRetriever, chunk, scripted_judge

OFENSA = '{"bloquear": true, "motivo": "OFENSA"}'
PII = '{"bloquear": true, "motivo": "PII"}'


def run(message: str, noul: str = '{"bloquear": false, "motivo": null}') -> tuple[dict, FakeChatModel, FakeChatModel, FakeRetriever]:
    judge_llm = FakeChatModel(responses=[scripted_judge("CONSULTA_RAG", '{"evidencia": "8h às 16h", "score": 5}', noul)] * 4)
    chat = FakeChatModel(responses=["A vacina é das 8h às 16h."])
    retriever = FakeRetriever([chunk("Vacina da gripe das 8h às 16h.")])
    deps = GraphDeps(retriever=retriever, chat_model=chat, judge=LLMJudge(judge_llm))
    state = build_graph(deps).invoke({"request_id": "req-1", "message": message, "history": [], "llm_calls": 0})
    return state, judge_llm, chat, retriever


def test_cpf_bloqueado_por_regex_sem_llm_nem_qdrant() -> None:  # AC-RF02-1
    state, judge_llm, chat, retriever = run("meu cpf é 123.456.789-09")
    assert state["route"] == "BLOQUEIO"
    assert state["guardrail"].model_dump() == {"motivo": "PII", "camada": "regex"}
    assert state["reply"] == BLOCK_REPLIES["PII"]
    assert state["llm_calls"] == 0
    assert judge_llm.calls == [] and chat.calls == [] and retriever.queries == []


def test_ofensa_bloqueada_pelo_llm_sem_choice_rag_ou_tools() -> None:  # AC-RF02-2
    state, judge_llm, chat, retriever = run("vocês são uns idiotas", noul=OFENSA)
    assert state["route"] == "BLOQUEIO"
    assert state["guardrail"].model_dump() == {"motivo": "OFENSA", "camada": "llm"}
    assert state["reply"] == BLOCK_REPLIES["OFENSA"]
    assert len(judge_llm.calls) == 1  # só o Noul
    assert chat.calls == [] and retriever.queries == []
    assert set(state["timings_ms"]) == {"noul", "resposta_bloqueio"}


def test_pii_semantica_bloqueada_pelo_llm() -> None:  # AC-RF02-3
    state, *_ = run("quero ver o histórico médico do paciente João da Silva", noul=PII)
    assert state["guardrail"].model_dump() == {"motivo": "PII", "camada": "llm"}


def test_pergunta_legitima_segue_para_choice() -> None:  # AC-RF02-4
    state, *_ = run("qual o horário da vacina da gripe?")
    assert state["route"] == "CONSULTA_RAG"
    assert state["guardrail"] is None
    assert "choice" in state["timings_ms"]


@pytest.mark.parametrize("bad", ["???", '{"bloquear": "talvez"}', '{"bloquear": true, "motivo": "SPAM"}'])
def test_noul_invalido_bloqueia_como_indeterminado(bad: str) -> None:
    state, judge_llm, *_ = run("mensagem estranha", noul=bad)
    assert state["guardrail"].motivo == "INDETERMINADO"
    assert state["reply"] == BLOCK_REPLIES["INDETERMINADO"]
    assert len(judge_llm.calls) == 2  # 1 nova tentativa


def test_bloqueio_com_urgencia_tambem_orienta_192() -> None:
    state, *_ = run("meu cpf é 123.456.789-09 e estou com dor no peito")
    assert state["guardrail"].motivo == "PII"
    assert "192" in state["reply"]


def test_log_de_bloqueio_nao_contem_o_texto(caplog: pytest.LogCaptureFixture) -> None:  # AC-RF02-5
    message = "meu cpf é 123.456.789-09"
    with caplog.at_level(logging.INFO):
        run(message)

    records = [r for r in caplog.records if r.getMessage() == "guardrail_block"]
    assert len(records) == 1
    record = records[0]
    assert (record.request_id, record.motivo, record.camada, record.message_len) == ("req-1", "PII", "regex", len(message))
    for r in caplog.records:
        dumped = f"{r.getMessage()} {r.__dict__}"
        assert "123.456.789-09" not in dumped and message not in dumped


@pytest.mark.parametrize(
    ("message", "noul"),
    [("Estou pensando em me matar", OFENSA), ("Meu filho bebeu produto de limpeza, acho que se envenenou", PII)],
)
def test_urgencia_nao_e_bloqueada_pelo_llm(message: str, noul: str) -> None:
    # Casos reais da avaliação: o Noul-LLM bloqueava essas urgências (ADR-07, revisão)
    state, judge_llm, *_ = run(message, noul=noul)
    assert state["route"] == "ATENDIMENTO_HUMANO" and state["guardrail"] is None
    assert "192" in state["reply"]
    assert judge_llm.calls == []
