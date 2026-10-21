"""Choice: urgência determinística, parsing, retry e histórico (SPEC RF02.2, ADR-07)."""

import pytest

from app.guardrails import URGENCY_TERMS, check_input, classify_intent, is_urgent, mentions_suicide
from app.judge import LLMJudge
from app.models import ChatTurn
from tests.fakes import FakeChatModel


@pytest.mark.parametrize(
    "message",
    [
        "estou com dor forte no peito e falta de ar",
        "Meu pai DESMAIOU e não acorda",
        "acho que é um AVC",
        "não consigo respirar direito",
        "meu filho está engasgado",
        "estou pensando em me matar",
        "sangramento que não para",
    ],
)
def test_urgencia_detectada_com_acentos_e_maiusculas(message: str) -> None:
    assert is_urgent(message)


@pytest.mark.parametrize(
    "message",
    ["qual o horário da vacina da gripe?", "quero marcar com um cardiologista", "a farmácia abre sábado?"],
)
def test_mensagens_comuns_nao_sao_urgencia(message: str) -> None:
    assert not is_urgent(message)


def test_lista_tem_os_18_termos_da_spec() -> None:
    assert len(URGENCY_TERMS) == 18


def test_suicidio_identificado_para_cvv() -> None:
    assert mentions_suicide("tenho pensamentos suicidas")
    assert not mentions_suicide("estou com dor no peito")


def test_urgencia_nao_chama_o_llm() -> None:
    llm = FakeChatModel()  # qualquer chamada falha o teste
    noul = check_input("estou com dor no peito", LLMJudge(llm))  # modo local: a regra decide antes do LLM
    assert (noul.urgent, noul.guardrail, noul.llm_calls) == (True, None, 0)
    decision = classify_intent("estou com dor no peito", [], LLMJudge(llm), urgent=noul.urgent)
    assert (decision.intent, decision.urgent, decision.llm_calls) == ("ATENDIMENTO_HUMANO", True, 0)
    assert llm.calls == []


def test_choice_valido_usa_uma_chamada() -> None:
    decision = classify_intent("quero marcar consulta", [], LLMJudge(FakeChatModel(responses=['{"intencao": "AGENDAMENTO"}'])))
    assert (decision.intent, decision.urgent, decision.llm_calls) == ("AGENDAMENTO", False, 1)


def test_choice_invalido_tenta_de_novo() -> None:
    llm = FakeChatModel(responses=["não sei", '{"intencao": "FORA_DO_NICHO"}'])
    assert LLMJudge(llm).choice("me indica um filme", []) == ("FORA_DO_NICHO", 2)


@pytest.mark.parametrize("bad", ['{"intencao": "VENDAS"}', "texto livre", '{"rota": "AGENDAMENTO"}'])
def test_choice_invalido_duas_vezes_vira_consulta_rag(bad: str) -> None:
    llm = FakeChatModel(responses=[bad, bad])
    assert LLMJudge(llm).choice("???", []) == ("CONSULTA_RAG", 2)


def test_choice_recebe_ultimos_4_turnos_truncados() -> None:
    llm = FakeChatModel(responses=['{"intencao": "AGENDAMENTO"}'])
    history = [ChatTurn(role="user", content=f"turno {i} " + "x" * 400) for i in range(6)]
    LLMJudge(llm).choice("e para pediatra?", history)

    prompt = llm.calls[0][-1].content
    assert "turno 0" not in prompt and "turno 1" not in prompt
    assert all(f"turno {i}" in prompt for i in range(2, 6))
    assert "x" * 301 not in prompt
    assert prompt.index("turno 5") < prompt.index("e para pediatra?")
