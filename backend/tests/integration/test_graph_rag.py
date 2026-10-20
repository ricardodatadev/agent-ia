"""Rota RAG com LLM e retriever falsos (AC-RF02-11, AC-RF02-12)."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.graph import GraphDeps, build_graph
from app.judge import LLMJudge
from app.models import ChatTurn
from app.prompts import FALLBACK_REPLY
from tests.fakes import FakeChatModel, FakeRetriever, chunk

JEJUM = chunk("Glicemia de jejum: jejum de 8 a 12 horas. Água é permitida.", section="Exames › Preparo")
SCORE_OK = '{"evidencia": "jejum de 8 a 12 horas", "score": 5}'
SCORE_SEM_EVIDENCIA = '{"evidencia": "nenhuma", "score": 1}'


def run(
    message: str,
    judge_llm: FakeChatModel,
    chat_llm: FakeChatModel,
    retriever: FakeRetriever,
    history: list[ChatTurn] | None = None,
) -> dict:
    judge_llm.responses.insert(0, '{"intencao": "CONSULTA_RAG"}')  # Choice antes do Score
    deps = GraphDeps(retriever=retriever, chat_model=chat_llm, judge=LLMJudge(judge_llm), top_k=3)
    return build_graph(deps).invoke({"request_id": "t", "message": message, "history": history or [], "llm_calls": 0})


def test_contexto_relevante_gera_resposta() -> None:  # AC-RF02-11
    chat = FakeChatModel(responses=["É preciso jejum de 8 a 12 horas."])
    retriever = FakeRetriever([JEJUM])
    state = run("Preciso de jejum para glicemia?", FakeChatModel(responses=[SCORE_OK]), chat, retriever)

    assert state["route"] == "CONSULTA_RAG"
    assert state["score"] == 5
    assert state["fallback"] is False
    assert state["reply"] == "É preciso jejum de 8 a 12 horas."
    assert state["contexts"] == [JEJUM]
    assert state["llm_calls"] == 3  # choice + score + generate
    assert retriever.queries == ["Preciso de jejum para glicemia?"]
    assert {"choice", "retrieve", "score", "generate"} <= set(state["timings_ms"])


def test_contexto_irrelevante_vai_para_fallback_sem_gerar() -> None:  # AC-RF02-12
    chat = FakeChatModel()  # qualquer chamada de geração falha o teste
    state = run("A UBS tem estacionamento?", FakeChatModel(responses=[SCORE_SEM_EVIDENCIA]), chat, FakeRetriever([JEJUM]))

    assert state["route"] == "CONSULTA_RAG"
    assert state["fallback"] is True
    assert state["reply"] == FALLBACK_REPLY
    assert state["score"] == 1
    assert state["llm_calls"] == 2  # choice + score
    assert chat.calls == []


def test_nota_alta_sem_evidencia_nao_gera() -> None:
    state = run("Tem estacionamento?", FakeChatModel(responses=['{"evidencia": "nenhuma", "score": 5}']), FakeChatModel(), FakeRetriever([JEJUM]))
    assert state["score"] == 2
    assert state["fallback"] is True


def test_sem_chunks_vai_direto_para_fallback() -> None:
    judge_llm, chat = FakeChatModel(), FakeChatModel()
    state = run("pergunta", judge_llm, chat, FakeRetriever([]))

    assert state["fallback"] is True
    assert state.get("score") is None
    assert len(judge_llm.calls) == 1 and chat.calls == []  # só o Choice
    assert state["llm_calls"] == 1


def test_score_invalido_vai_para_fallback() -> None:
    state = run("pergunta", FakeChatModel(responses=["???"]), FakeChatModel(), FakeRetriever([JEJUM]))
    assert state["score"] == 1
    assert state["fallback"] is True


def test_prompt_de_geracao_tem_sistema_contexto_e_pergunta() -> None:
    chat = FakeChatModel(responses=["ok"])
    run("Preciso de jejum?", FakeChatModel(responses=[SCORE_OK]), chat, FakeRetriever([JEJUM]))

    messages = chat.calls[0]
    assert isinstance(messages[0], SystemMessage)
    assert "SOMENTE com base no CONTEXTO" in messages[0].content
    prompt = messages[-1].content
    assert "exames.md — Exames › Preparo" in prompt
    assert "jejum de 8 a 12 horas" in prompt
    assert prompt.rstrip().endswith("Preciso de jejum?")


def test_historico_entra_na_geracao() -> None:
    chat = FakeChatModel(responses=["ok"])
    history = [ChatTurn(role="user", content="Tem pediatra?"), ChatTurn(role="assistant", content="Sim.")]
    run("E o jejum para glicemia?", FakeChatModel(responses=[SCORE_OK]), chat, FakeRetriever([JEJUM]), history)

    messages = chat.calls[0]
    assert isinstance(messages[1], HumanMessage) and messages[1].content == "Tem pediatra?"
    assert isinstance(messages[2], AIMessage) and messages[2].content == "Sim."


def test_top_k_limita_os_chunks() -> None:
    chunks = [chunk(f"jejum de 8 a 12 horas {i}", index=i) for i in range(5)]
    state = run("jejum?", FakeChatModel(responses=[SCORE_OK]), FakeChatModel(responses=["ok"]), FakeRetriever(chunks))
    assert len(state["contexts"]) == 3
