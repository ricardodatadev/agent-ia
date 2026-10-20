"""Contrato HTTP de /chat e /health (SPEC §5.3, RNF04)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_chat_retorna_contrato_valido(client: TestClient) -> None:
    resp = client.post("/chat", json={"message": "Qual o horário da UBS?"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "request_id", "reply", "route", "guardrail", "tool_call", "score", "fallback", "sources",
    }


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
