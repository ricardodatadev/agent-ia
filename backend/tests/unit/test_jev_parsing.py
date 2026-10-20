"""Parsing das decisões do modo local e Score ancorado em evidência (SPEC RF02.3, ADR-11)."""

import pytest

from app.judge import LLMJudge, ScoreVerdict, anchored_score, evidence_found, evidence_on_topic, parse_verdict
from tests.fakes import FakeChatModel, chunk

CHUNKS = [
    chunk("Glicemia de jejum: jejum de 8 a 12 horas. Água é permitida."),
    chunk("Especialidades não oferecidas na UBS são acessadas por encaminhamento para a rede especializada."),
]
Q = "Preciso de jejum para exame de glicemia?"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"evidencia": "x", "score": 4}', ScoreVerdict(evidencia="x", score=4)),
        ('Claro! {"score": "5", "evidencia": "x"} espero ter ajudado', ScoreVerdict(evidencia="x", score=5)),
        ('{"score": 3}', ScoreVerdict(evidencia="", score=3)),
    ],
)
def test_parse_verdict_valido(text: str, expected: ScoreVerdict) -> None:
    assert parse_verdict(text, ScoreVerdict) == expected


@pytest.mark.parametrize("text", ["", "não sei", '{"score": 7}', '{"score": 0}', '{"score": "alto"}', "{score: 3", "[1, 2]"])
def test_parse_verdict_invalido_ou_fora_do_dominio(text: str) -> None:
    assert parse_verdict(text, ScoreVerdict) is None


def test_evidencia_literal_e_encontrada() -> None:
    assert evidence_found("jejum de 8 a 12 horas", CHUNKS)


def test_evidencia_tolera_acentos_e_pequenas_diferencas() -> None:
    assert evidence_found("Glicemia de jejum: jejum de 8 a 12 horas, agua permitida", CHUNKS)


@pytest.mark.parametrize("evidence", ["", "nenhuma", "Nenhuma.", "A UBS tem estacionamento gratuito para pacientes"])
def test_evidencia_ausente_ou_inventada(evidence: str) -> None:
    assert not evidence_found(evidence, CHUNKS)


def test_nota_baixa_com_evidencia_sobe_para_3() -> None:
    assert anchored_score(ScoreVerdict(evidencia="jejum de 8 a 12 horas", score=2), CHUNKS, Q) == 3


def test_nota_alta_sem_evidencia_cai_para_2() -> None:
    assert anchored_score(ScoreVerdict(evidencia="nenhuma", score=5), CHUNKS, Q) == 2
    assert anchored_score(ScoreVerdict(evidencia="frase que não existe nos trechos", score=4), CHUNKS, Q) == 2


def test_nota_coerente_e_mantida() -> None:
    assert anchored_score(ScoreVerdict(evidencia="jejum de 8 a 12 horas", score=5), CHUNKS, Q) == 5
    assert anchored_score(ScoreVerdict(evidencia="nenhuma", score=1), CHUNKS, Q) == 1


def test_score_invalido_vira_1_falha_segura() -> None:
    judge = LLMJudge(FakeChatModel(responses=["não é JSON"]))
    assert judge.score("Preciso de jejum?", CHUNKS) == (1, 1)


def test_prompt_do_score_tem_pergunta_depois_do_contexto() -> None:
    llm = FakeChatModel(responses=['{"evidencia": "nenhuma", "score": 1}'])
    LLMJudge(llm).score("Preciso de jejum?", CHUNKS)
    prompt = llm.calls[0][-1].content
    assert prompt.index("jejum de 8 a 12 horas") < prompt.index("Preciso de jejum?")


@pytest.mark.parametrize(
    ("question", "evidence"),
    [
        ("Quais documentos preciso levar na consulta?", "Documento oficial com foto (RG, CNH ou carteira de trabalho)"),
        ("Qual o horário da vacina da gripe?", "a vacina da gripe é aplicada de segunda a sexta"),
        ("Tem dentista na UBS?", "Odontologia (dentista)"),
    ],
)
def test_evidencia_sobre_o_assunto_da_pergunta(question: str, evidence: str) -> None:
    assert evidence_on_topic(question, evidence)


def test_frase_real_de_outro_assunto_nao_conta_como_evidencia() -> None:
    # Caso real (Llama 3.2): citou uma frase existente, mas sem relação com a pergunta, e deu nota 4.
    question = "A UBS aceita plano de saúde particular?"
    evidence = "Especialidades não oferecidas na UBS são acessadas por encaminhamento para a rede especializada."
    assert evidence_found(evidence, CHUNKS)
    assert not evidence_on_topic(question, evidence)
    assert anchored_score(ScoreVerdict(evidencia=evidence, score=4), CHUNKS, question) == 2


def test_titulo_da_secao_conta_como_assunto_da_evidencia() -> None:
    chunks = [chunk("A UBS funciona de segunda a sexta-feira, das 7h às 19h.", section="Funcionamento da UBS › Horário de atendimento")]
    verdict = ScoreVerdict(evidencia="A UBS funciona de segunda a sexta-feira, das 7h às 19h.", score=5)
    assert anchored_score(verdict, chunks, "Qual o horário da UBS?") == 5


def test_titulo_do_documento_nao_conta_como_assunto() -> None:
    chunks = [chunk("Aos sábados, funciona das 8h às 12h apenas para vacinação.", section="Funcionamento da UBS › Horário de atendimento")]
    verdict = ScoreVerdict(evidencia="Aos sábados, das 8h às 12h apenas para vacinação.", score=4)
    assert anchored_score(verdict, chunks, "A UBS Jardim Esperança aceita plano de saúde?") == 2


@pytest.mark.parametrize(
    ("responses", "expected"),
    [
        (['{"bloquear": false, "motivo": null}'], (None, 1)),
        (['{"bloquear": false, "motivo": "PII"}'], (None, 1)),  # aprovada: motivo é ignorado
        (['{"bloquear": true, "motivo": "OFENSA"}'], ("OFENSA", 1)),
        (['{"bloquear": true, "motivo": "PII"}'], ("PII", 1)),
        (['{"bloquear": true, "motivo": null}'], ("INDETERMINADO", 1)),  # bloqueio sem motivo
        (["lixo", '{"bloquear": true, "motivo": "PII"}'], ("PII", 2)),  # 1 nova tentativa
        (["lixo", "lixo"], ("INDETERMINADO", 2)),  # falha segura
    ],
)
def test_noul_modo_local(responses: list[str], expected: tuple) -> None:
    assert LLMJudge(FakeChatModel(responses=responses)).noul("mensagem") == expected
