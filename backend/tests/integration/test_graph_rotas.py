"""Roteamento do grafo por intenção, com LLM e retriever falsos (AC-RF02-6..9, RNF01)."""

import pytest

from app.graph import GraphDeps, build_graph
from app.judge import LLMJudge
from app.prompts import OUT_OF_SCOPE_REPLY
from tests.fakes import FakeChatModel, FakeRetriever, chunk, scripted_judge

DOCS = chunk("Leve documento com foto, Cartão SUS e comprovante de residência.", section="Documentos necessários para consulta")


def run(message: str, intencao: str) -> tuple[dict, FakeChatModel, FakeChatModel, FakeRetriever]:
    judge_llm = FakeChatModel(responses=[scripted_judge(intencao, '{"evidencia": "documento com foto", "score": 5}')] * 3)
    chat = FakeChatModel(responses=["Leve documento com foto e Cartão SUS."])
    retriever = FakeRetriever([DOCS])
    deps = GraphDeps(retriever=retriever, chat_model=chat, judge=LLMJudge(judge_llm))
    state = build_graph(deps).invoke({"request_id": "t", "message": message, "history": [], "llm_calls": 0})
    return state, judge_llm, chat, retriever


def test_duvida_vai_para_rag() -> None:  # AC-RF02-6
    state, _, chat, retriever = run("quais documentos preciso levar na consulta?", "CONSULTA_RAG")
    assert state["route"] == "CONSULTA_RAG"
    assert retriever.queries and len(chat.calls) == 1


def test_agendamento_vai_para_tool_sem_rag() -> None:  # AC-RF02-7
    state, _, chat, retriever = run("quero marcar com um cardiologista", "AGENDAMENTO")
    assert state["route"] == "AGENDAMENTO"
    assert "tool_agendamento" in state["timings_ms"]
    assert retriever.queries == [] and chat.calls == []


def test_urgencia_vai_para_atendimento_com_192_mesmo_com_llm_errando() -> None:  # AC-RF02-8
    state, judge_llm, _, retriever = run("estou com dor forte no peito e falta de ar", "FORA_DO_NICHO")
    assert state["route"] == "ATENDIMENTO_HUMANO"
    assert state["urgent"] is True
    assert "192" in state["reply"]
    assert judge_llm.calls == [] and retriever.queries == []
    assert state["llm_calls"] == 0


def test_atendimento_sem_urgencia_tambem_orienta_192() -> None:
    state, *_ = run("quero falar com a enfermeira", "ATENDIMENTO_HUMANO")
    assert state["route"] == "ATENDIMENTO_HUMANO" and state["urgent"] is False
    assert "192" in state["reply"]


def test_fora_do_nicho_resposta_fixa_sem_rag_nem_tools() -> None:  # AC-RF02-9
    state, _, chat, retriever = run("qual a capital da França?", "FORA_DO_NICHO")
    assert state["route"] == "FORA_DO_NICHO"
    assert state["reply"] == OUT_OF_SCOPE_REPLY
    assert retriever.queries == [] and chat.calls == []
    assert state["llm_calls"] == 1
    assert not {"retrieve", "tool_agendamento", "tool_atendente"} & set(state["timings_ms"])


@pytest.mark.parametrize(
    ("intencao", "max_calls"),
    [("CONSULTA_RAG", 3), ("AGENDAMENTO", 1), ("ATENDIMENTO_HUMANO", 1), ("FORA_DO_NICHO", 1)],
)
def test_chamadas_ao_llm_por_rota(intencao: str, max_calls: int) -> None:  # RNF01 (Noul entra na T-08)
    state, *_ = run("mensagem qualquer sobre documentos", intencao)
    assert state["llm_calls"] == max_calls
