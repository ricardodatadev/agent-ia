"""Arquivos de perguntas do Jev: carga, validação pelo SDK e conferência contra o grafo (AC-RF06-4)."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from typesafe_sdk import Choice, Noul, Score

from app.config import Settings
from app.jev import JEVS_DIR, JevConfigError, JevQuestions, resolve_engine, score_from_level


@pytest.fixture
def jevs(tmp_path: Path) -> Path:
    for f in JEVS_DIR.glob("*.json"):
        shutil.copy(f, tmp_path / f.name)
    return tmp_path


def edit(directory: Path, name: str, change: Any) -> None:
    path = directory / f"{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_arquivos_do_projeto_carregam_com_os_modelos_do_sdk() -> None:
    q = JevQuestions.load()
    assert set(q.noul) == {"ofensa", "pii", "urgencia"} and all(isinstance(v, Noul) for v in q.noul.values())
    assert isinstance(q.choice["intencao"], Choice)
    assert set(q.choice["intencao"].criteria) == {"CONSULTA_RAG", "AGENDAMENTO", "ATENDIMENTO_HUMANO", "FORA_DO_NICHO"}
    assert isinstance(q.score["relevancia"], Score) and len(q.score["relevancia"].criteria) == 5


def test_opcao_do_choice_faltando(jevs: Path) -> None:
    edit(jevs, "choice", lambda d: d["intencao"]["criteria"].pop("FORA_DO_NICHO"))
    with pytest.raises(JevConfigError, match=r"faltando \['FORA_DO_NICHO'\]"):
        JevQuestions.load(jevs)


def test_opcao_do_choice_sobrando(jevs: Path) -> None:
    edit(jevs, "choice", lambda d: d["intencao"]["criteria"].update({"VENDAS": "Quer comprar algo."}))
    with pytest.raises(JevConfigError, match=r"sobrando \['VENDAS'\]"):
        JevQuestions.load(jevs)


def test_score_com_numero_errado_de_niveis(jevs: Path) -> None:
    edit(jevs, "score", lambda d: d["relevancia"]["criteria"].pop())
    with pytest.raises(JevConfigError, match="precisa de 5 níveis"):
        JevQuestions.load(jevs)


def test_campo_desconhecido_e_rejeitado_pelo_sdk(jevs: Path) -> None:
    edit(jevs, "noul", lambda d: d["ofensa"].update({"temperature": 0}))
    with pytest.raises(JevConfigError, match="noul.json: pergunta 'ofensa' inválida"):
        JevQuestions.load(jevs)


def test_tipo_errado_e_rejeitado(jevs: Path) -> None:
    edit(jevs, "score", lambda d: d["relevancia"].update({"type": "choice"}))
    with pytest.raises(JevConfigError, match="score.json"):
        JevQuestions.load(jevs)


def test_pergunta_do_noul_faltando(jevs: Path) -> None:
    edit(jevs, "noul", lambda d: d.pop("pii"))
    with pytest.raises(JevConfigError, match="noul.json: esperadas as perguntas"):
        JevQuestions.load(jevs)


def test_json_invalido_e_arquivo_ausente(jevs: Path) -> None:
    (jevs / "choice.json").write_text("{ quebrado", encoding="utf-8")
    with pytest.raises(JevConfigError, match="choice.json: JSON inválido"):
        JevQuestions.load(jevs)
    (jevs / "choice.json").unlink()
    with pytest.raises(JevConfigError, match="não encontrado"):
        JevQuestions.load(jevs)


@pytest.mark.parametrize(("level", "score"), [(0, 1), (0.4, 1), (1.6, 3), (2, 3), (3.5, 5), (4, 5)])
def test_nivel_do_jev_vira_nota_1_a_5(level: float, score: int) -> None:
    assert score_from_level(level) == score


@pytest.mark.parametrize(
    ("provider", "key", "engine"),
    [("auto", "k", "typesafe"), ("auto", None, "llm"), ("auto", "", "llm"), ("llm", "k", "llm"), ("typesafe", "k", "typesafe")],
)
def test_escolha_do_motor(provider: str, key: str | None, engine: str) -> None:  # AC-RF06-1, AC-RF06-2
    assert resolve_engine(Settings(jev_provider=provider, typesafe_api_key=key)) == engine


def test_typesafe_sem_chave_falha_citando_a_variavel() -> None:  # AC-RF06-3
    with pytest.raises(JevConfigError, match="TYPESAFE_API_KEY"):
        resolve_engine(Settings(jev_provider="typesafe"))


def test_pergunta_de_urgencia_faltando(jevs: Path) -> None:
    edit(jevs, "noul", lambda d: d.pop("urgencia"))
    with pytest.raises(JevConfigError, match="noul.json: esperadas as perguntas"):
        JevQuestions.load(jevs)
