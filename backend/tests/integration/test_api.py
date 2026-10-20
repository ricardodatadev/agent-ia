"""Contrato HTTP de /chat e /health (SPEC §5.3, RNF04)."""

import pytest
from fastapi.testclient import TestClient

from app.graph import GraphDeps
from app.judge import LLMJudge
from app.main import create_app
from tests.fakes import FakeChatModel, FakeRetriever, chunk, scripted_judge


@pytest.fixture
def client() -> TestClient:
    deps = GraphDeps(
        retriever=FakeRetriever([chunk("A UBS funciona das 7h às 19h.", source="funcionamento.md", section="Horário de atendimento")]),
        chat_model=FakeChatModel(responses=["A UBS funciona das 7h às 19h."] * 10),
        judge=LLMJudge(FakeChatModel(responses=[scripted_judge(score='{"evidencia": "A UBS funciona das 7h às 19h", "score": 5}')] * 20)),
    )
    return TestClient(create_app(deps=deps))


def test_chat_retorna_contrato_valido(client: TestClient) -> None:
    resp = client.post("/chat", json={"message": "Qual o horário da UBS?"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "request_id", "reply", "route", "guardrail", "tool_call", "score", "fallback", "sources",
    }
    assert body["route"] == "CONSULTA_RAG"
    assert body["score"] == 5 and body["fallback"] is False
    assert body["reply"] == "A UBS funciona das 7h às 19h."
    assert body["sources"] == [
        {"source": "funcionamento.md", "section": "Horário de atendimento", "snippet": "A UBS funciona das 7h às 19h."}
    ]


def test_request_id_unico_por_requisicao(client: TestClient) -> None:
    ids = {client.post("/chat", json={"message": "oi"}).json()["request_id"] for _ in range(2)}
    assert len(ids) == 2


@pytest.mark.parametrize("message", ["", "x" * 1001])
def test_chat_rejeita_mensagem_fora_do_limite(client: TestClient, message: str) -> None:
    assert client.post("/chat", json={"message": message}).status_code == 422


def test_chat_rejeita_historico_maior_que_6(client: TestClient) -> None:
    history = [{"role": "user", "content": "oi"}] * 7
    resp = client.post("/chat", json={"message": "oi", "history": history})
    assert resp.status_code == 422


def test_openapi_expoe_contratos(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert {"ChatRequest", "ChatResponse"} <= set(schemas)


def test_cors_restrito_as_origens_configuradas(client: TestClient) -> None:
    headers = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"}
    assert client.options("/chat", headers=headers).headers.get("access-control-allow-origin")
    headers["Origin"] = "http://evil.example"
    assert "access-control-allow-origin" not in client.options("/chat", headers=headers).headers


def test_fallback_nao_retorna_fontes() -> None:
    deps = GraphDeps(
        retriever=FakeRetriever([chunk("A UBS funciona das 7h às 19h.")]),
        chat_model=FakeChatModel(),
        judge=LLMJudge(FakeChatModel(responses=[scripted_judge()] * 2)),
    )
    body = TestClient(create_app(deps=deps)).post("/chat", json={"message": "Tem estacionamento?"}).json()
    assert body["fallback"] is True
    assert body["sources"] == []
