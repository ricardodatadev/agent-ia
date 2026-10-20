"""Nós das tools com LLM falso (AC-RF03-1..4, AC-RF02-8, ADR-04)."""

from app.graph import GraphDeps, build_graph
from app.judge import LLMJudge
from tests.fakes import FakeChatModel, FakeRetriever, scripted_judge, tool_call

AGENDAR = "agendar_consulta_especialista"
ATENDENTE = "encaminhar_atendente_humano"


def run(message: str, intencao: str, *chat_responses: object) -> tuple[dict, FakeChatModel]:
    chat = FakeChatModel(responses=list(chat_responses))
    judge = LLMJudge(FakeChatModel(responses=[scripted_judge(intencao)] * 3))
    deps = GraphDeps(retriever=FakeRetriever(), chat_model=chat, judge=judge)
    state = build_graph(deps).invoke({"request_id": "t", "message": message, "history": [], "llm_calls": 0})
    return state, chat


def test_agenda_cardiologia_com_protocolo() -> None:  # AC-RF03-1
    state, chat = run("quero marcar com um cardiologista", "AGENDAMENTO", tool_call(AGENDAR, especialidade="cardiologista"))
    tc = state["tool_call"]
    assert tc.name == AGENDAR
    assert tc.args == {"especialidade": "cardiologia"}
    assert tc.result.sucesso is True
    assert tc.result.protocolo in state["reply"]
    assert "clínico geral" in state["reply"]  # cardiologia exige avaliação prévia
    assert chat.bound_tools == [[AGENDAR]]  # só a tool da rota
    assert state["llm_calls"] == 3  # noul + choice + extração


def test_sinonimo_extraido_pelo_llm_e_normalizado() -> None:
    state, _ = run("preciso de um médico do coração", "AGENDAMENTO", tool_call(AGENDAR, especialidade="médico do coração"))
    assert state["tool_call"].args == {"especialidade": "cardiologia"}


def test_llm_sem_tool_call_usa_a_mensagem() -> None:
    state, _ = run("quero consulta com pediatra pro meu filho", "AGENDAMENTO", "Claro, vou agendar.")
    assert state["tool_call"].args == {"especialidade": "pediatria"}


def test_sem_especialidade_pede_esclarecimento() -> None:  # AC-RF03-2
    state, _ = run("quero marcar uma consulta", "AGENDAMENTO", tool_call(AGENDAR, especialidade=""))
    assert state["tool_call"] is None
    assert "Com qual especialidade" in state["reply"]
    assert "Cardiologia" in state["reply"] and "Pediatria" in state["reply"]


def test_especialidade_indisponivel_lista_as_disponiveis() -> None:  # AC-RF03-3
    state, _ = run("quero marcar com um neurocirurgião", "AGENDAMENTO", tool_call(AGENDAR, especialidade="neurocirurgião"))
    assert state["tool_call"] is None
    assert "não é atendida na UBS" in state["reply"]
    assert "Clínico geral" in state["reply"]


def test_tool_call_com_outro_nome_e_ignorada() -> None:
    state, _ = run("quero marcar uma consulta", "AGENDAMENTO", tool_call("apagar_banco", especialidade="cardiologia"))
    assert state["tool_call"] is None
    assert "Com qual especialidade" in state["reply"]


def test_atendente_com_motivo_extraido() -> None:  # AC-RF03-4
    state, chat = run(
        "quero falar com a enfermeira sobre meu curativo",
        "ATENDIMENTO_HUMANO",
        tool_call(ATENDENTE, motivo="Dúvida sobre curativo", urgente=False),
    )
    tc = state["tool_call"]
    assert tc.name == ATENDENTE
    assert tc.args == {"motivo": "Dúvida sobre curativo", "urgente": False}
    assert tc.result.protocolo in state["reply"]
    assert "192" in state["reply"]
    assert chat.bound_tools == [[ATENDENTE]]


def test_urgencia_encaminha_sem_llm_com_192() -> None:  # AC-RF03-4, AC-RF02-8
    state, chat = run("estou com dor forte no peito e falta de ar", "FORA_DO_NICHO")
    tc = state["tool_call"]
    assert tc.name == ATENDENTE and tc.args["urgente"] is True
    assert len(tc.args["motivo"]) >= 3
    assert "192" in state["reply"] and "prioridade" in state["reply"]
    assert chat.calls == []
    assert state["llm_calls"] == 0  # urgência: nem Noul-LLM, nem Choice, nem extração


def test_urgencia_sem_palavra_chave_marcada_pelo_llm() -> None:
    state, _ = run("minha mãe está muito pálida e confusa", "ATENDIMENTO_HUMANO", tool_call(ATENDENTE, motivo="Mãe pálida e confusa", urgente=True))
    assert state["tool_call"].args["urgente"] is True


def test_motivo_invalido_nao_impede_encaminhamento() -> None:
    state, _ = run("atendente", "ATENDIMENTO_HUMANO", tool_call(ATENDENTE, motivo="", urgente=False))
    assert state["tool_call"].args["motivo"] == "Solicitação do paciente: atendente"
    assert state["tool_call"].result.sucesso is True


def test_mencao_a_suicidio_inclui_cvv() -> None:
    state, _ = run("estou pensando em me matar", "ATENDIMENTO_HUMANO")
    assert "188" in state["reply"] and "192" in state["reply"]
