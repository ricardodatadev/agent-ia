"""Rede municipal de saúde: documentos, pergunta ambígua e UBS de referência (RF08, T-30)."""

import re

from app.prompts import GENERATE_SYSTEM, HEALTH_INFO_PREFIX, handoff_reply, schedule_confirmed_reply
from app.rag import DATA_DIR, chunk_text

UNIDADES = ("UBS Jardim Esperança", "UBS Vila Nova", "UBS Santa Clara")
REDE_DOCS = [p for p in sorted(DATA_DIR.glob("*.md")) if not p.name.startswith(HEALTH_INFO_PREFIX)]


def test_documentos_da_rede_sao_ficticios_e_sem_nome_de_cidade() -> None:  # AC-RF08-1
    assert {p.name for p in REDE_DOCS} == {"especialidades.md", "exames.md", "funcionamento.md", "unidades.md", "vacinas.md"}
    for path in REDE_DOCS:
        text = path.read_text(encoding="utf-8")
        assert "Documento fictício" in text, path.name
        assert not re.search(r"(Prefeitura|Município|Cidade) de [A-ZÀ-Ú]", text), path.name
    unidades = (DATA_DIR / "unidades.md").read_text(encoding="utf-8")
    assert all(u in unidades for u in UNIDADES)


def test_resumo_de_horarios_cabe_em_um_trecho_com_as_tres_ubs() -> None:  # base da resposta à pergunta ambígua
    chunks = chunk_text((DATA_DIR / "unidades.md").read_text(encoding="utf-8"))
    resumo = [c for c in chunks if "Resumo de horários" in (c.section or "")]
    assert len(resumo) == 1
    assert all(u.removeprefix("UBS ") in resumo[0].text for u in UNIDADES)


def test_geracao_nunca_escolhe_uma_unidade_sozinha() -> None:  # AC-RF08-3 (regra; o efeito é medido no eval)
    assert "Nunca escolha uma unidade por conta própria" in GENERATE_SYSTEM


def test_respostas_remetem_a_ubs_de_referencia_sem_pedir_endereco() -> None:  # AC-RF08-4
    for reply in (
        schedule_confirmed_reply("Cardiologia", "AGD-1", needs_referral=True),
        schedule_confirmed_reply("Pediatria", "AGD-2", needs_referral=False),
        handoff_reply("ATD-1", urgent=False),
    ):
        assert "UBS de referência" in reply
        assert "endereço" not in reply.lower()
