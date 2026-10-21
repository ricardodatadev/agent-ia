"""JevJudge pelo SDK oficial com a rede simulada (httpx2.MockTransport) — AC-RF06-1, 5 e 6."""

import json
import logging
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from typesafe_sdk import RetryPolicy, TypeSafeClient

from app.config import Settings
from app.graph import GraphDeps, build_graph
from app.jev import JEVS_DIR, JevConfigError, JevJudge, JevQuestions
from app.main import CONFIG_ERROR_DETAIL, UNAVAILABLE_DETAIL, build_judge, create_app
from app.models import ChatTurn
from tests.fakes import FakeChatModel, FakeRetriever, chunk

QUESTIONS = JevQuestions.load()
Handler = Callable[[httpx2.Request], httpx2.Response]


def answers_response(answers: dict[str, Any], status: int = 200) -> httpx2.Response:
    body = {"model": "jev-1.13.0", "usage": {"input_tokens": 150, "output_tokens": 4}, "answers": answers}
    return httpx2.Response(status, json=body, headers={"x-typesafe-request-id": "req-jev"})


def noul(ofensa: float, pii: float, urgencia: float = 0.02) -> dict[str, Any]:
    return {
        "ofensa": {"type": "noul", "noul": ofensa},
        "pii": {"type": "noul", "noul": pii},
        "urgencia": {"type": "noul", "noul": urgencia},
    }


def choice(label: str, confidence: float = 0.9) -> dict[str, Any]:
    return {"intencao": {"type": "choice", "choice": label, "confidence": confidence, "probabilities": {label: confidence}}}


def score(level: float, confidence: float = 0.9) -> dict[str, Any]:
    legend = {str(i): f"nível {i}" for i in range(5)}
    probs = {str(i): 0.2 for i in range(5)}
    return {"relevancia": {"type": "score", "score": level, "confidence": confidence, "legend": legend, "probabilities": probs}}


def fail(exc: Exception) -> Handler:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise exc

    return handler


class Recorder:
    """Responde conforme a pergunta enviada (ou via função) e grava cada requisição."""

    def __init__(self, routes: dict[str, Any] | Handler) -> None:
        self.routes = routes
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if callable(self.routes):
            return self.routes(request)
        asked = set(json.loads(request.content)["questions"])
        for key, answers in self.routes.items():
            if key in asked:
                return answers_response(answers)
        raise AssertionError(f"pergunta inesperada: {asked}")

    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests]


def judge_with(recorder: Recorder, **kwargs: Any) -> JevJudge:
    client = TypeSafeClient(
        api_key="ts-test-key", model="jev-1.13.0", transport=httpx2.MockTransport(recorder), retry=RetryPolicy(max_retries=0)
    )
    return JevJudge(client, QUESTIONS, "jev-1.13.0", **kwargs)


def file_questions(name: str) -> dict[str, Any]:
    return json.loads((JEVS_DIR / f"{name}.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- contrato (AC-RF06-6)


def test_requisicao_segue_o_contrato_da_api() -> None:
    rec = Recorder({"ofensa": noul(0.01, 0.02)})
    judge_with(rec).noul("qual o horário da vacina?")
    request = rec.requests[0]
    assert request.method == "POST" and request.url.path == "/v1/systemone"
    assert request.headers["authorization"] == "Bearer ts-test-key"
    body = json.loads(request.content)
    assert body["model"] == "jev-1.13.0"
    assert body["state"] == "qual o horário da vacina?"
    assert body["questions"] == file_questions("noul")


def test_perguntas_do_choice_e_do_score_sao_iguais_aos_arquivos() -> None:
    rec = Recorder({"intencao": choice("CONSULTA_RAG"), "relevancia": score(4)})
    judge = judge_with(rec)
    judge.choice("oi", [])
    judge.score("oi", [chunk("texto")])
    assert [b["questions"] for b in rec.bodies()] == [file_questions("choice"), file_questions("score")]


# --------------------------------------------------------------------------- Noul


@pytest.mark.parametrize(
    ("probs", "expected"),
    [((0.02, 0.03), None), ((0.91, 0.10), "OFENSA"), ((0.05, 0.88), "PII"), ((0.60, 0.95), "PII"), ((0.5, 0.1), "OFENSA")],
)
def test_noul_bloqueia_pelo_maior_valor_acima_do_limiar(probs: tuple[float, float], expected: str | None) -> None:
    result = judge_with(Recorder({"ofensa": noul(*probs)})).noul("msg")
    assert (result.motivo, result.urgent, result.calls) == (expected, False, 1)


def test_limiar_configuravel() -> None:
    result = judge_with(Recorder({"ofensa": noul(0.7, 0.1)}), noul_threshold=0.8).noul("msg")
    assert (result.motivo, result.calls) == (None, 1)


def test_resposta_sem_uma_das_perguntas_vira_indeterminado() -> None:
    rec = Recorder({"ofensa": {"ofensa": {"type": "noul", "noul": 0.01}}})
    result = judge_with(rec).noul("msg")
    assert (result.motivo, result.urgent, result.calls) == ("INDETERMINADO", None, 1)


# --------------------------------------------------------------------------- Choice


def test_choice_envia_state_estruturado_com_historico_recente() -> None:
    rec = Recorder({"intencao": choice("AGENDAMENTO")})
    history = [ChatTurn(role="user", content=f"turno {i} " + "x" * 400) for i in range(5)]
    history.append(ChatTurn(role="assistant", content="Qual especialidade?"))
    assert judge_with(rec).choice("e para pediatra?", history) == ("AGENDAMENTO", 1)
    state = rec.bodies()[0]["state"]
    assert state["mensagem_atual"] == "e para pediatra?"
    assert len(state["historico"]) == 4
    assert state["historico"][-1] == {"autor": "assistente", "texto": "Qual especialidade?"}
    assert all(len(t["texto"]) <= 300 for t in state["historico"])


def test_choice_fora_das_rotas_vira_consulta_rag() -> None:
    assert judge_with(Recorder({"intencao": choice("VENDAS")})).choice("msg", []) == ("CONSULTA_RAG", 1)


# --------------------------------------------------------------------------- Score


@pytest.mark.parametrize(("level", "expected"), [(0.1, 1), (1.2, 2), (2.0, 3), (3.4, 4), (3.9, 5)])
def test_score_nivel_vira_nota(level: float, expected: int) -> None:
    assert judge_with(Recorder({"relevancia": score(level)})).score("pergunta", [chunk("t")]) == (expected, 1)


def test_score_envia_pergunta_e_trechos_com_fonte() -> None:
    rec = Recorder({"relevancia": score(4)})
    judge_with(rec).score("Preciso de jejum?", [chunk("Jejum de 8 a 12 horas.", source="exames.md")])
    assert rec.bodies()[0]["state"] == {
        "pergunta": "Preciso de jejum?",
        "trechos": [{"fonte": "exames.md", "texto": "Jejum de 8 a 12 horas."}],
    }


def test_score_com_confianca_baixa_vai_para_fallback() -> None:
    assert judge_with(Recorder({"relevancia": score(4, confidence=0.3)})).score("p", [chunk("t")]) == (1, 1)


# --------------------------------------------------------------------------- grafo completo (AC-RF06-1)


def run_graph(rec: Recorder, message: str, chat: FakeChatModel | None = None) -> dict[str, Any]:
    deps = GraphDeps(
        retriever=FakeRetriever([chunk("A vacina da gripe é das 8h às 16h.", source="vacinas.md")]),
        chat_model=chat or FakeChatModel(responses=["A vacina é das 8h às 16h."]),
        judge=judge_with(rec),
    )
    return build_graph(deps).invoke({"request_id": "t", "message": message, "history": [], "llm_calls": 0})


def test_bloqueio_semantico_pelo_jev_informa_camada_jev() -> None:
    state = run_graph(Recorder({"ofensa": noul(0.97, 0.01)}), "vocês são uns idiotas")
    assert state["route"] == "BLOQUEIO"
    assert state["guardrail"].model_dump() == {"motivo": "OFENSA", "camada": "jev"}


def test_rag_completo_com_jev() -> None:
    rec = Recorder({"ofensa": noul(0.01, 0.01), "intencao": choice("CONSULTA_RAG"), "relevancia": score(3.8)})
    state = run_graph(rec, "Qual o horário da vacina da gripe?")
    assert state["route"] == "CONSULTA_RAG" and state["score"] == 5 and state["fallback"] is False
    assert state["llm_calls"] == 4  # 3 decisões no Jev + geração no LLM
    assert len(rec.requests) == 3


@pytest.mark.parametrize(
    "message",
    ["meu cpf é 123.456.789-09", "meu cpf é 123 456 789 09", "me liga no 11 98765 4321", "meu email é maria arroba gmail ponto com"],
)
def test_pii_por_regex_nao_chama_o_jev(message: str) -> None:  # AC-RF02-16
    rec = Recorder(fail(AssertionError("não deveria chamar o Jev")))
    state = run_graph(rec, message)
    assert state["guardrail"].model_dump() == {"motivo": "PII", "camada": "regex"}
    assert rec.requests == []


# --------------------------------------------------------------------------- erros na API (AC-RF06-5)


def api_client(handler: Handler) -> TestClient:
    deps = GraphDeps(retriever=FakeRetriever(), chat_model=FakeChatModel(), judge=judge_with(Recorder(handler)))
    return TestClient(create_app(deps=deps, health_probe=lambda: {}))


@pytest.mark.parametrize(
    "handler",
    [
        fail(httpx2.ConnectError("sem rede")),
        fail(httpx2.ReadTimeout("lento")),
        lambda r: httpx2.Response(429, json={"error": "rate limit"}),
        lambda r: httpx2.Response(503, json={"error": "indisponível"}),
        lambda r: httpx2.Response(200, json={"answers": "malformado"}),
    ],
    ids=["conexao", "timeout", "429", "5xx", "malformada"],
)
def test_jev_indisponivel_retorna_503(handler: Handler) -> None:
    resp = api_client(handler).post("/chat", json={"message": "qual o horário da vacina?"})
    assert resp.status_code == 503 and resp.json() == {"detail": UNAVAILABLE_DETAIL}


def test_chave_invalida_do_jev_retorna_500(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        resp = api_client(lambda r: httpx2.Response(401, json={"error": "invalid api key"})).post("/chat", json={"message": "oi"})
    assert resp.status_code == 500 and resp.json() == {"detail": CONFIG_ERROR_DETAIL}
    record = next(r for r in caplog.records if r.getMessage() == "llm_config_error")
    assert record.dependency == "jev"


# --------------------------------------------------------------------------- LGPD (AC-RF06-6)


def test_logs_nao_contem_o_texto_da_mensagem(caplog: pytest.LogCaptureFixture) -> None:
    message = "Minha vizinha Maria Souza está com HIV?"
    with caplog.at_level(logging.DEBUG):
        state = run_graph(Recorder({"ofensa": noul(0.02, 0.97)}), message)
    assert state["guardrail"].motivo == "PII"
    assert logging.getLogger("typesafe_sdk").level == logging.WARNING  # o SDK registra corpos em DEBUG
    answer = next(r for r in caplog.records if r.getMessage() == "jev_answer")
    assert answer.jev_model == "jev-1.13.0" and answer.input_tokens == 150
    assert answer.nouls == {"ofensa": 0.02, "pii": 0.97, "urgencia": 0.02}
    for r in caplog.records:
        assert "Maria Souza" not in f"{r.getMessage()} {r.__dict__}"


# --------------------------------------------------------------------------- escolha do motor na inicialização


def startup_records(caplog: pytest.LogCaptureFixture, **settings: Any) -> tuple[Any, list[logging.LogRecord]]:
    with caplog.at_level(logging.INFO):
        judge = build_judge(Settings(**settings))
    return judge, [r for r in caplog.records if r.getMessage() == "decision_engine_selected"]


def test_auto_com_chave_usa_o_jev(caplog: pytest.LogCaptureFixture) -> None:  # AC-RF06-1
    judge, records = startup_records(caplog, jev_provider="auto", typesafe_api_key="ts-key")
    assert isinstance(judge, JevJudge) and judge.layer == "jev"
    assert (records[0].engine, records[0].model) == ("typesafe", "jev-1.13.0")
    judge.close()


def test_auto_sem_chave_usa_modo_local_e_registra_no_log(caplog: pytest.LogCaptureFixture) -> None:  # AC-RF06-2
    judge, records = startup_records(caplog, jev_provider="auto")
    assert judge.layer == "llm"
    assert (records[0].engine, records[0].reason) == ("llm", "auto: sem TYPESAFE_API_KEY")


def test_typesafe_sem_chave_impede_a_subida() -> None:  # AC-RF06-3
    with pytest.raises(JevConfigError, match="TYPESAFE_API_KEY"):
        create_app(settings=Settings(jev_provider="typesafe"))


# --------------------------------------------------------------------------- urgência pelo Jev (T-26)


def test_urgencia_pelo_jev_sem_termo_da_lista() -> None:  # AC-RF06-8
    rec = Recorder({"ofensa": noul(0.01, 0.02, urgencia=0.9)})
    chat = FakeChatModel()  # qualquer chamada falha o teste
    state = run_graph(rec, "estou com um aperto no peito muito forte", chat=chat)
    assert state["route"] == "ATENDIMENTO_HUMANO" and state["urgent"] is True
    assert state["tool_call"].args["urgente"] is True and "192" in state["reply"]
    assert len(rec.requests) == 1 and chat.calls == []  # só o Noul: sem Choice e sem extração no LLM
    assert state["llm_calls"] == 1


@pytest.mark.parametrize(("urgencia", "urgent"), [(0.29, False), (0.3, True), (0.9, True)])
def test_limiar_de_urgencia_e_menor_que_o_de_bloqueio(urgencia: float, urgent: bool) -> None:
    result = judge_with(Recorder({"ofensa": noul(0.01, 0.01, urgencia)})).noul("msg")
    assert result.urgent is urgent and result.motivo is None


def test_limiar_de_urgencia_configuravel() -> None:
    result = judge_with(Recorder({"ofensa": noul(0.01, 0.01, 0.5)}), urgency_threshold=0.8).noul("msg")
    assert result.urgent is False


def test_urgencia_passa_a_frente_do_bloqueio_semantico() -> None:
    rec = Recorder({"ofensa": noul(0.97, 0.90, urgencia=0.8)})
    state = run_graph(rec, "estou muito mal e vocês são uns idiotas, preciso de ajuda", chat=FakeChatModel())
    assert state["route"] == "ATENDIMENTO_HUMANO" and state["guardrail"] is None


@pytest.mark.parametrize(
    "message",
    ["o que é um AVC?", "meu pai teve um infarto há 10 anos", "nunca tive dor no peito, só queria saber o horário"],
)
def test_com_urgencia_baixa_a_regra_de_termos_nao_e_consultada(message: str) -> None:  # AC-RF06-9
    rec = Recorder({"ofensa": noul(0.01, 0.01, urgencia=0.04), "intencao": choice("CONSULTA_RAG"), "relevancia": score(3.5)})
    state = run_graph(rec, message)
    assert state["route"] == "CONSULTA_RAG" and state["urgent"] is False
    assert len(rec.requests) == 3  # Noul, Choice e Score no Jev


def test_a_regra_erraria_nesses_casos_mas_o_jev_evita() -> None:
    from app.guardrails import is_urgent

    assert is_urgent("o que é um AVC?") and is_urgent("meu pai teve um infarto há 10 anos")


def test_sem_resposta_de_urgencia_do_jev_decide_a_regra() -> None:
    sem_urgencia = {"ofensa": {"type": "noul", "noul": 0.01}, "pii": {"type": "noul", "noul": 0.01}}
    rec = Recorder({"ofensa": sem_urgencia, "intencao": choice("CONSULTA_RAG"), "relevancia": score(3.5)})
    assert run_graph(rec, "estou com dor no peito", chat=FakeChatModel())["urgent"] is True
    assert run_graph(rec, "qual o horário da vacina?")["urgent"] is False


# --------------------------------------------------------------------------- plano B: Jev fora do ar (AC-RF06-5)

CAIDAS = [
    fail(httpx2.ConnectError("sem rede")),
    fail(httpx2.ReadTimeout("lento")),
    lambda r: httpx2.Response(503, json={"error": "indisponível"}),
    lambda r: httpx2.Response(401, json={"error": "invalid api key"}),
]


@pytest.mark.parametrize("handler", CAIDAS, ids=["conexao", "timeout", "5xx", "chave_recusada"])
def test_jev_fora_do_ar_com_urgencia_a_regra_atende(handler: Handler, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        resp = api_client(handler).post("/chat", json={"message": "estou com dor no peito"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["route"] == "ATENDIMENTO_HUMANO" and body["tool_call"]["args"]["urgente"] is True
    assert "192" in body["reply"]
    record = next(r for r in caplog.records if r.getMessage() == "urgency_fallback")
    assert "dor no peito" not in f"{record.getMessage()} {record.__dict__}"  # LGPD: só metadados


@pytest.mark.parametrize("message", ["qual o horário da vacina?", "não estou com dor no peito"])
def test_jev_fora_do_ar_sem_urgencia_continua_503(message: str) -> None:
    resp = api_client(fail(httpx2.ConnectError("sem rede"))).post("/chat", json={"message": message})
    assert resp.status_code == 503 and resp.json() == {"detail": UNAVAILABLE_DETAIL}


def test_erro_de_programacao_nao_e_engolido_pelo_plano_b() -> None:
    deps = GraphDeps(retriever=FakeRetriever(), chat_model=FakeChatModel(), judge=judge_with(Recorder(fail(ValueError("bug")))))
    client = TestClient(create_app(deps=deps, health_probe=lambda: {}), raise_server_exceptions=False)
    assert client.post("/chat", json={"message": "estou com dor no peito"}).status_code == 500
