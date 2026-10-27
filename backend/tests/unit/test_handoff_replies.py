"""Respostas de agendamento e encaminhamento só prometem o que o sistema faz (T-29)."""

from typing import Any

import pytest

from app.graph import GraphDeps, build_graph
from app.judge import LLMJudge
from app.prompts import EMERGENCY_NOTICE, handoff_reply, schedule_confirmed_reply
from app.text import normalize
from app.tools import TOOL_ATENDENTE
from tests.fakes import FakeChatModel, FakeRetriever, scripted_judge, tool_call

PROMESSAS = ("entrar em contato", "retornar", "aguarde")  # ninguém liga nem entra no chat sem transferência ao vivo


def promete_contato(reply: str) -> bool:
    return any(p in normalize(reply) for p in PROMESSAS)


def test_sem_transferencia_ao_vivo_a_resposta_orienta_levar_o_protocolo() -> None:
    for reply in (
        schedule_confirmed_reply("Cardiologia", "AGD-1", needs_referral=True),
        handoff_reply("ATD-1", urgent=False),
    ):
        assert not promete_contato(reply)
        assert "recepção" in reply and "protocolo" in reply


def test_com_transferencia_ao_vivo_a_resposta_pede_para_aguardar() -> None:
    assert "Aguarde" in schedule_confirmed_reply("Pediatria", "AGD-1", needs_referral=False, live=True)
    assert "Aguarde" in handoff_reply("ATD-1", urgent=False, live=True)


@pytest.mark.parametrize("live", [False, True])
def test_urgencia_comeca_pelo_192_e_nunca_pede_para_aguardar(live: bool) -> None:
    reply = handoff_reply("ATD-1", urgent=True, live=live)
    assert reply.startswith(EMERGENCY_NOTICE)
    assert "prioridade" in reply and "ATD-1" in reply
    assert not promete_contato(reply)


def run(handoff_live: bool) -> dict[str, Any]:
    deps = GraphDeps(
        retriever=FakeRetriever(),
        chat_model=FakeChatModel(responses=[tool_call(TOOL_ATENDENTE, motivo="quer falar com a enfermagem", urgente=False)]),
        judge=LLMJudge(FakeChatModel(responses=[scripted_judge("ATENDIMENTO_HUMANO")] * 2)),
        handoff_live=handoff_live,
    )
    return build_graph(deps).invoke({"request_id": "t", "message": "quero falar com a enfermeira", "history": [], "llm_calls": 0})


def test_o_grafo_usa_a_configuracao_de_transferencia() -> None:
    assert not promete_contato(run(handoff_live=False)["reply"])
    assert "Aguarde" in run(handoff_live=True)["reply"]
