"""Pergunta de horário sem unidade decidida no código (AC-RF08-3, AC-RF08-5, T-32)."""

import pytest

from app.graph import GraphDeps, build_graph
from app.guardrails import asks_network_hours
from app.judge import LLMJudge
from app.models import ChatTurn
from app.rag import hours_summary
from tests.fakes import FakeChatModel, FakeRetriever, chunk, scripted_judge


@pytest.mark.parametrize(
    "message",
    [
        "Até que horas o posto fica aberto?",
        "Que horas a UBS abre?",
        "Qual o horário de funcionamento da UBS?",
        "Qual UBS abre no sábado?",
        "Qual unidade fica aberta até mais tarde?",
    ],
)
def test_horario_sem_unidade_e_ambiguo(message: str) -> None:
    assert asks_network_hours(message, [])


@pytest.mark.parametrize(
    "message",
    [
        "A UBS Vila Nova abre no sábado?",  # unidade citada
        "Que horas é a vacina da gripe na UBS?",  # serviço citado
        "Até que horas posso fazer a coleta de exames na unidade?",
        "Que horas a farmácia municipal abre?",
        "Como funciona o cadastro na UBS?",  # não é pergunta de horário
        "Quais documentos levo na UBS?",
        "Quanto tempo demora o resultado dos exames?",
    ],
)
def test_pergunta_com_unidade_servico_ou_sem_horario_segue_o_rag(message: str) -> None:  # AC-RF08-5
    assert not asks_network_hours(message, [])


def test_unidade_dita_antes_na_conversa_segue_o_rag() -> None:
    history = [ChatTurn(role="user", content="Minha UBS é a Santa Clara"), ChatTurn(role="assistant", content="Certo!")]
    assert not asks_network_hours("Até que horas a UBS fica aberta?", history)


def test_resumo_de_horarios_vem_do_documento() -> None:
    summary = hours_summary()
    assert summary is not None and summary.source == "unidades.md"
    assert all(u in summary.text for u in ("Jardim Esperança", "Vila Nova", "Santa Clara", "UPA 24h"))


def run(message: str, history: list[ChatTurn] | None = None, **deps_overrides: object) -> tuple[dict, FakeChatModel, FakeRetriever]:
    chat = FakeChatModel()
    retriever = FakeRetriever()
    judge = LLMJudge(FakeChatModel(responses=[scripted_judge("CONSULTA_RAG")] * 3))
    options = {"hours_summary": hours_summary(), **deps_overrides}
    deps = GraphDeps(retriever=retriever, chat_model=chat, judge=judge, **options)
    state = build_graph(deps).invoke({"request_id": "t", "message": message, "history": history or [], "llm_calls": 0})
    return state, chat, retriever


def test_pergunta_ambigua_responde_o_resumo_sem_score_nem_geracao() -> None:  # AC-RF08-3
    state, chat, retriever = run("Até que horas o posto fica aberto?")
    assert state["route"] == "CONSULTA_RAG" and state["fallback"] is False
    assert state["reply"].startswith("O horário depende da unidade.")
    assert all(u in state["reply"] for u in ("Jardim Esperança", "Vila Nova", "Santa Clara"))
    assert [c.source for c in state["contexts"]] == ["unidades.md"]  # fonte exibida na UI
    assert chat.calls == [] and retriever.queries == []
    assert state["llm_calls"] == 2  # só Noul e Choice


def test_pergunta_com_unidade_passa_pelo_rag() -> None:  # AC-RF08-5
    state, _, retriever = run("A UBS Vila Nova abre no sábado?")
    assert retriever.queries == ["A UBS Vila Nova abre no sábado?"]
    assert state["fallback"] is True  # retriever vazio: fallback de sempre


def test_sem_resumo_carregado_segue_o_rag() -> None:
    state, _, retriever = run("Que horas a UBS abre?", hours_summary=None)
    assert retriever.queries and state["fallback"] is True


def test_outra_rota_nao_e_desviada() -> None:
    chat = FakeChatModel()
    judge = LLMJudge(FakeChatModel(responses=[scripted_judge("FORA_DO_NICHO")] * 3))
    deps = GraphDeps(retriever=FakeRetriever([chunk("x")]), chat_model=chat, judge=judge, hours_summary=hours_summary())
    state = build_graph(deps).invoke({"request_id": "t", "message": "Que horas a UBS abre?", "history": [], "llm_calls": 0})
    assert state["route"] == "FORA_DO_NICHO" and not state["reply"].startswith("O horário depende")
