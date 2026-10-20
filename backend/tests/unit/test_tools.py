"""Contratos, normalização e mocks das tools (SPEC RF03, ADR-08, Apêndice C.3)."""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.rag import DATA_DIR
from app.text import normalize
from app.tools import (
    ESPECIALIDADES,
    AgendarConsultaArgs,
    EncaminharAtendenteArgs,
    agendar_consulta_especialista,
    encaminhar_atendente_humano,
    normalize_especialidade,
    resolve_especialidade,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("cardiologista", "cardiologia"),
        ("médico do coração", "cardiologia"),
        ("dentista", "odontologia"),
        ("Pediatra pro meu filho", "pediatria"),
        ("ginecologista", "ginecologia"),
        ("problema de pele", "dermatologia"),
        ("psicólogo", "psicologia"),
        ("nutricionista", "nutricao"),
        ("clínico geral", "clinico_geral"),
        ("neurocirurgião", None),
        ("", None),
    ],
)
def test_normaliza_especialidade(text: str, expected: str | None) -> None:
    assert normalize_especialidade(text) == expected


def test_lista_igual_a_dos_documentos() -> None:
    doc = normalize((DATA_DIR / "especialidades.md").read_text(encoding="utf-8"))
    for label in ESPECIALIDADES.values():
        assert normalize(label.split(" (")[0]) in doc


def test_llm_vazio_usa_a_mensagem() -> None:
    assert resolve_especialidade("", "quero marcar com um cardiologista") == ("ok", "cardiologia")


@pytest.mark.parametrize("extracted", ["", "consulta", "médico", None])
def test_sem_especialidade_e_ausente(extracted: str | None) -> None:
    assert resolve_especialidade(extracted, "quero marcar uma consulta") == ("ausente", None)


def test_especialidade_fora_da_lista_e_indisponivel() -> None:
    assert resolve_especialidade("neurocirurgião", "quero marcar com um neurocirurgião") == ("indisponivel", None)


def test_args_rejeitam_especialidade_fora_da_lista() -> None:
    with pytest.raises(ValidationError):
        AgendarConsultaArgs(especialidade="neurologia")  # type: ignore[arg-type]


@pytest.mark.parametrize("motivo", ["", "ok", "x" * 201])
def test_motivo_do_atendente_validado(motivo: str) -> None:
    with pytest.raises(ValidationError):
        EncaminharAtendenteArgs(motivo=motivo)


def test_protocolos_tem_formato_da_spec() -> None:
    agd = agendar_consulta_especialista(AgendarConsultaArgs(especialidade="cardiologia"))
    atd = encaminhar_atendente_humano(EncaminharAtendenteArgs(motivo="dor forte", urgente=True))
    assert agd.sucesso and atd.sucesso
    assert re.fullmatch(r"AGD-\d{8}-[0-9A-F]{4}", agd.protocolo)
    assert re.fullmatch(r"ATD-\d{8}-[0-9A-F]{4}", atd.protocolo)
    assert agd.tool == "agendar_consulta_especialista" and atd.tool == "encaminhar_atendente_humano"


def test_tools_nao_fazem_io(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("I/O inesperado")

    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr("socket.socket", forbidden)
    agendar_consulta_especialista(AgendarConsultaArgs(especialidade="pediatria"))
    encaminhar_atendente_humano(EncaminharAtendenteArgs(motivo="quero falar com a enfermeira"))
