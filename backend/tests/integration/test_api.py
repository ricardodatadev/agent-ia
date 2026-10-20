"""Contrato HTTP de /chat e /health (SPEC §5.3, RNF04)."""

import json
import logging
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import DependencyUnavailable
from app.graph import GraphDeps
from app.judge import LLMJudge
from app.main import UNAVAILABLE_DETAIL, JsonFormatter, create_app
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
        judge=LLMJudge(FakeChatModel(responses=[scripted_judge()] * 3)),
    )
    body = TestClient(create_app(deps=deps)).post("/chat", json={"message": "Tem estacionamento?"}).json()
    assert body["fallback"] is True
    assert body["sources"] == []


# --------------------------------------------------------------------------- resiliência (RNF05)

class BrokenRetriever:
    def search(self, query: str, top_k: int) -> list:
        raise DependencyUnavailable("qdrant", "ConnectError")


class BrokenChatModel(FakeChatModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[no-untyped-def]
        raise httpx.ConnectError("conexão recusada")


def test_llm_indisponivel_retorna_503_amigavel() -> None:
    deps = GraphDeps(retriever=FakeRetriever(), chat_model=FakeChatModel(), judge=LLMJudge(BrokenChatModel()))
    resp = TestClient(create_app(deps=deps)).post("/chat", json={"message": "qual o horário?"})
    assert resp.status_code == 503
    assert resp.json() == {"detail": UNAVAILABLE_DETAIL}
    assert "Traceback" not in resp.text


def test_qdrant_indisponivel_retorna_503() -> None:
    judge = LLMJudge(FakeChatModel(responses=[scripted_judge()] * 2))
    deps = GraphDeps(retriever=BrokenRetriever(), chat_model=FakeChatModel(), judge=judge)
    resp = TestClient(create_app(deps=deps)).post("/chat", json={"message": "qual o horário?"})
    assert resp.status_code == 503 and resp.json() == {"detail": UNAVAILABLE_DETAIL}


def test_bloqueio_por_regex_funciona_com_llm_fora_e_em_menos_de_50ms() -> None:  # RNF02
    deps = GraphDeps(retriever=BrokenRetriever(), chat_model=BrokenChatModel(), judge=LLMJudge(BrokenChatModel()))
    client = TestClient(create_app(deps=deps))
    client.post("/chat", json={"message": "aquecimento 123.456.789-09"})
    start = time.perf_counter()
    resp = client.post("/chat", json={"message": "meu cpf é 123.456.789-09"})
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert resp.status_code == 200 and resp.json()["guardrail"] == {"motivo": "PII", "camada": "regex"}
    assert elapsed_ms < 50


def test_clientes_reais_sem_servicos_retornam_503() -> None:
    settings = Settings(ollama_base_url="http://127.0.0.1:1", qdrant_url="http://127.0.0.1:1", llm_timeout_s=3)
    client = TestClient(create_app(settings=settings))
    assert client.post("/chat", json={"message": "qual o horário da vacina?"}).status_code == 503
    health = client.get("/health")
    assert health.status_code == 503
    assert health.json() | {"collection_points": None} == {
        "status": "degradado", "qdrant": "erro", "ollama": "erro", "collection_points": None,
    }


# --------------------------------------------------------------------------- health


def test_health_ok_com_componentes() -> None:
    probe = lambda: {"qdrant": "ok", "ollama": "ok", "collection_points": 32}  # noqa: E731
    deps = GraphDeps(retriever=FakeRetriever(), chat_model=FakeChatModel(), judge=LLMJudge(FakeChatModel()))
    resp = TestClient(create_app(deps=deps, health_probe=probe)).get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "qdrant": "ok", "ollama": "ok", "collection_points": 32}


def test_health_503_se_componente_falha() -> None:
    probe = lambda: {"qdrant": "erro", "ollama": "ok", "collection_points": None}  # noqa: E731
    deps = GraphDeps(retriever=FakeRetriever(), chat_model=FakeChatModel(), judge=LLMJudge(FakeChatModel()))
    assert TestClient(create_app(deps=deps, health_probe=probe)).get("/health").status_code == 503


# --------------------------------------------------------------------------- observabilidade (RNF06)


def test_log_por_requisicao_com_metadados_e_sem_texto(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    message = "Qual o horário da UBS?"
    with caplog.at_level(logging.INFO):
        body = client.post("/chat", json={"message": message}).json()

    record = next(r for r in caplog.records if r.getMessage() == "chat_request")
    line = json.loads(JsonFormatter().format(record))
    assert line["event"] == "chat_request"
    assert line["request_id"] == body["request_id"]
    assert line["route"] == "CONSULTA_RAG" and line["score"] == 5 and line["tool"] is None
    assert line["llm_calls"] == 4
    assert {"noul", "choice", "retrieve", "score", "generate"} <= set(line["timings_ms"])
    assert line["total_ms"] > 0 and line["message_len"] == len(message) and line["history_len"] == 0
    assert all(message not in json.dumps(json.loads(JsonFormatter().format(r)), ensure_ascii=False) for r in caplog.records)
