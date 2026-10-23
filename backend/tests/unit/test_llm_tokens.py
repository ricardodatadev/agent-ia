"""Registro de tokens por decisão no LLMJudge (RNF06, T-27) e a soma feita pelo avaliador."""

import logging

import pytest
from langchain_core.messages import AIMessage

from app.judge import LLMJudge
from tests.eval.run_eval import TokenCollector, compute_metrics, load_dataset
from tests.fakes import FakeChatModel, chunk

MENSAGEM = "meu vizinho Carlos Pereira tem diabetes?"


def com_tokens(text: str, entrada: int, saida: int) -> AIMessage:
    return AIMessage(content=text, usage_metadata={"input_tokens": entrada, "output_tokens": saida, "total_tokens": entrada + saida})


def eventos(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == "llm_answer"]


def test_noul_registra_tokens_e_nao_o_texto(caplog: pytest.LogCaptureFixture) -> None:
    llm = FakeChatModel(responses=[com_tokens('{"bloquear": true, "motivo": "PII"}', 321, 9)])
    with caplog.at_level(logging.INFO):
        result = LLMJudge(llm).noul(MENSAGEM)
    assert result.motivo == "PII"

    (evento,) = eventos(caplog)
    assert (evento.decision, evento.input_tokens, evento.output_tokens) == ("noul", 321, 9)
    for record in caplog.records:  # LGPD: nem a mensagem nem o prompt vão para o log
        assert "Carlos" not in f"{record.getMessage()} {record.__dict__}"


def test_cada_decisao_tem_o_seu_rotulo(caplog: pytest.LogCaptureFixture) -> None:
    llm = FakeChatModel(
        responses=[
            com_tokens('{"intencao": "AGENDAMENTO"}', 500, 6),
            com_tokens('{"evidencia": "nenhuma", "score": 1}', 900, 12),
        ]
    )
    judge = LLMJudge(llm)
    with caplog.at_level(logging.INFO):
        judge.choice("quero marcar consulta", [])
        judge.score("tem estacionamento?", [chunk("A UBS funciona das 7h às 19h.")])
    assert [(e.decision, e.input_tokens, e.output_tokens) for e in eventos(caplog)] == [("choice", 500, 6), ("score", 900, 12)]


def test_nova_tentativa_gera_um_evento_por_chamada(caplog: pytest.LogCaptureFixture) -> None:
    llm = FakeChatModel(responses=[com_tokens("lixo", 300, 4), com_tokens('{"bloquear": false, "motivo": null}', 300, 8)])
    with caplog.at_level(logging.INFO):
        assert LLMJudge(llm).noul("qual o horário?").calls == 2
    assert len(eventos(caplog)) == 2


def test_modelo_sem_contagem_de_tokens_nao_quebra(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        LLMJudge(FakeChatModel(responses=['{"bloquear": false, "motivo": null}'])).noul("qual o horário?")
    (evento,) = eventos(caplog)
    assert evento.input_tokens is None and evento.output_tokens is None


# --------------------------------------------------------------------------- soma no avaliador


def test_coletor_soma_por_decisao_e_so_dos_eventos_de_tokens() -> None:
    collector = TokenCollector()
    logger = logging.getLogger("teste.tokens")
    logger.setLevel(logging.INFO)
    logger.addHandler(collector)
    try:
        logger.info("llm_answer", extra={"decision": "noul", "input_tokens": 300, "output_tokens": 8})
        logger.info("llm_answer", extra={"decision": "noul", "input_tokens": 300, "output_tokens": 4})
        logger.info("jev_answer", extra={"decision": "choice", "input_tokens": 150, "output_tokens": 2})
        logger.info("chat_request", extra={"decision": "noul", "input_tokens": 9999, "output_tokens": 9999})  # outro evento: ignorado
        logger.info("llm_answer", extra={"decision": "score", "input_tokens": None, "output_tokens": None})
    finally:
        logger.removeHandler(collector)

    assert collector.by_decision == {
        "noul": {"calls": 2, "input": 600, "output": 12},
        "choice": {"calls": 1, "input": 150, "output": 2},
        "score": {"calls": 1, "input": 0, "output": 0},
    }
    collector.reset()
    assert collector.by_decision == {}


def test_metricas_somam_tokens_por_decisao_e_por_mensagem() -> None:
    cases = load_dataset()
    base = {
        "route": "CONSULTA_RAG", "guardrail": None, "score": 5, "fallback": False, "tool": None,
        "llm_calls": 1, "timings_ms": {}, "total_s": 1.0,
    }
    results = [
        {**base, "id": c["id"], "decision_tokens": {"noul": {"calls": 1, "input": 100, "output": 10}}}
        for c in cases
    ]
    metrics, _ = compute_metrics(cases, results)
    assert metrics["Tokens por decisão (média por chamada)"] == "noul 100 entrada / 10 saída"
    assert metrics["Tokens das decisões (média por mensagem)"] == "100 entrada / 10 saída"
    assert metrics["Tokens das decisões (total)"] == "5000 entrada / 500 saída em 50 chamadas"


def test_sem_dados_de_tokens_as_metricas_nao_mostram_linhas_de_tokens() -> None:
    cases = load_dataset()
    base = {
        "route": "CONSULTA_RAG", "guardrail": None, "score": 5, "fallback": False, "tool": None,
        "llm_calls": 1, "timings_ms": {}, "total_s": 1.0,
    }
    metrics, _ = compute_metrics(cases, [{**base, "id": c["id"]} for c in cases])
    assert not any(name.startswith("Tokens") for name in metrics)
