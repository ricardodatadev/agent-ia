"""Trava de negação da regra de urgência e orquestração do Noul (SPEC RF02.1, Apêndice C.2, T-26)."""

import pytest
from typesafe_sdk import TypeSafeAPIConnectionError

from app.guardrails import check_input, is_urgent, urgency_signal
from app.judge import NoulResult
from app.models import GuardrailLayer


@pytest.mark.parametrize(
    "message",
    [
        "não estou com dor no peito",
        "NÃO ESTOU COM DOR NO PEITO",
        "nunca tive dor no peito",
        "estou sem dor no peito",
        "não estou com mais nenhuma dor no peito",
        "não estou sentindo nenhuma falta de ar",
    ],
)
def test_negacao_colada_ao_termo_faz_a_regra_se_abster(message: str) -> None:  # AC-RF02-14
    assert urgency_signal(message) == "negated"
    assert not is_urgent(message)


@pytest.mark.parametrize(
    "message",
    [
        "Não estou com meus documentos e tenho uma dor no peito",  # o "não" nega os documentos
        "Tenho uma dor no peito e não estou com meus documentos",
        "não sei o horário, mas estou com dor no peito",
        "não aguento essa dor no peito",
        "não tenho dor de cabeça, mas tenho dor no peito",
        "não estou com dor no peito, mas estou com falta de ar",
        "semana que vem tenho dor no peito",  # "sem" dentro de outra palavra não é negação
        "não consigo respirar",  # o "não" faz parte do próprio termo
        "meu pai não acorda",
    ],
)
def test_negacao_que_nao_se_refere_ao_sintoma_nao_trava_a_regra(message: str) -> None:  # AC-RF02-15
    assert urgency_signal(message) == "urgent"


def test_sem_termo_nao_ha_sinal() -> None:
    assert urgency_signal("qual o horário da vacina da gripe?") == "none"


@pytest.mark.parametrize("message", ["o que é um AVC?", "meu pai teve um infarto há 10 anos"])
def test_limitacao_conhecida_a_regra_nao_distingue_pergunta_informativa(message: str) -> None:
    # Documentado na SPEC (RF02.1): com o Jev ativo, quem distingue é a pergunta `urgencia`.
    assert urgency_signal(message) == "urgent"


# --------------------------------------------------------------------------- check_input com um juiz fictício


class StubJudge:
    """Juiz que devolve um resultado fixo ou levanta um erro; grava as chamadas."""

    def __init__(self, decides_urgency: bool, result: NoulResult | None = None, error: Exception | None = None) -> None:
        self.decides_urgency = decides_urgency
        self.layer: GuardrailLayer = "jev" if decides_urgency else "llm"
        self.result = result
        self.error = error
        self.messages: list[str] = []

    def noul(self, message: str) -> NoulResult:
        self.messages.append(message)
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result

    def choice(self, message, history):  # type: ignore[no-untyped-def]
        raise AssertionError("não deveria chamar o Choice")

    def score(self, question, chunks):  # type: ignore[no-untyped-def]
        raise AssertionError("não deveria chamar o Score")


def test_com_o_jev_a_regra_nao_e_consultada() -> None:
    judge = StubJudge(decides_urgency=True, result=NoulResult(None, False, 1))
    decision = check_input("o que é um AVC?", judge)  # a regra erraria; o Jev decidiu que não é urgência
    assert (decision.urgent, decision.guardrail, decision.llm_calls) == (False, None, 1)


def test_com_o_jev_urgencia_sem_termo_da_lista() -> None:
    judge = StubJudge(decides_urgency=True, result=NoulResult(None, True, 1))
    assert check_input("estou com um aperto no peito muito forte", judge).urgent is True


def test_no_modo_local_a_regra_decide_antes_do_llm() -> None:
    judge = StubJudge(decides_urgency=False, result=NoulResult("OFENSA", None, 1))
    decision = check_input("estou com dor no peito", judge)
    assert decision.urgent is True and judge.messages == []  # nem chegou a chamar o Noul-LLM


def test_no_modo_local_negacao_segue_para_o_llm() -> None:
    judge = StubJudge(decides_urgency=False, result=NoulResult(None, None, 1))
    decision = check_input("não estou com dor no peito", judge)
    assert decision.urgent is False and len(judge.messages) == 1


def test_plano_b_quando_o_jev_falha_e_a_regra_reconhece_a_urgencia() -> None:
    judge = StubJudge(decides_urgency=True, error=TypeSafeAPIConnectionError("sem rede"))
    decision = check_input("estou com dor no peito", judge)
    assert (decision.urgent, decision.llm_calls) == (True, 0)


@pytest.mark.parametrize("message", ["qual o horário da vacina?", "não estou com dor no peito"])
def test_sem_urgencia_o_erro_do_jev_continua_subindo(message: str) -> None:
    judge = StubJudge(decides_urgency=True, error=TypeSafeAPIConnectionError("sem rede"))
    with pytest.raises(TypeSafeAPIConnectionError):
        check_input(message, judge)


def test_erro_de_programacao_nao_vira_plano_b() -> None:
    judge = StubJudge(decides_urgency=True, error=ValueError("bug"))
    with pytest.raises(ValueError):
        check_input("estou com dor no peito", judge)
