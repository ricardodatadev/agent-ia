"""Rota RAG com LLM e retriever falsos (AC-RF02-11)."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.graph import GraphDeps, build_graph
from app.models import ChatTurn
from tests.fakes import FakeChatModel, FakeRetriever, chunk

JEJUM = chunk("Glicemia de jejum: jejum de 8 a 12 horas. Água é permitida.", section="Exames › Preparo")


def run(message: str, llm: FakeChatModel, retriever: FakeRetriever, history: list[ChatTurn] | None = None) -> dict:
    graph = build_graph(GraphDeps(retriever=retriever, chat_model=llm, top_k=3))
    return graph.invoke({"request_id": "t", "message": message, "history": history or [], "llm_calls": 0})


def test_resposta_gerada_a_partir_do_contexto() -> None:
    llm = FakeChatModel(responses=["É preciso jejum de 8 a 12 horas."])
    retriever = FakeRetriever([JEJUM])
    state = run("Preciso de jejum para glicemia?", llm, retriever)

    assert state["route"] == "CONSULTA_RAG"
    assert state["reply"] == "É preciso jejum de 8 a 12 horas."
    assert state["contexts"] == [JEJUM]
    assert state["llm_calls"] == 1
    assert retriever.queries == ["Preciso de jejum para glicemia?"]
    assert {"retrieve", "generate"} <= set(state["timings_ms"])


def test_prompt_tem_sistema_contexto_e_pergunta() -> None:
    llm = FakeChatModel(responses=["ok"])
    run("Preciso de jejum?", llm, FakeRetriever([JEJUM]))

    messages = llm.calls[0]
    assert isinstance(messages[0], SystemMessage)
    assert "SOMENTE com base no CONTEXTO" in messages[0].content
    prompt = messages[-1].content
    assert "exames.md — Exames › Preparo" in prompt
    assert "jejum de 8 a 12 horas" in prompt
    assert prompt.rstrip().endswith("Preciso de jejum?")


def test_historico_entra_na_geracao() -> None:
    llm = FakeChatModel(responses=["ok"])
    history = [ChatTurn(role="user", content="Tem pediatra?"), ChatTurn(role="assistant", content="Sim.")]
    run("E qual o horário?", llm, FakeRetriever([JEJUM]), history)

    messages = llm.calls[0]
    assert isinstance(messages[1], HumanMessage) and messages[1].content == "Tem pediatra?"
    assert isinstance(messages[2], AIMessage) and messages[2].content == "Sim."


def test_top_k_limita_os_chunks() -> None:
    chunks = [chunk(f"texto {i}", index=i) for i in range(5)]
    state = run("pergunta", FakeChatModel(responses=["ok"]), FakeRetriever(chunks))
    assert len(state["contexts"]) == 3
