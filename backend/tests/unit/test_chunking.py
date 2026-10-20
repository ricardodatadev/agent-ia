"""Chunking e IDs determinísticos (SPEC RF01)."""

from app.rag import CHUNK_OVERLAP, CHUNK_SIZE, DATA_DIR, chunk_text, point_id, split_sections

DOC = """# Exames

> Documento fictício.

## Coleta de sangue

A coleta acontece de segunda a sexta.

### Preparo

- Glicemia: jejum de 8 a 12 horas.

## Resultados

Entregues presencialmente.
"""


def test_secao_e_o_caminho_de_titulos() -> None:
    sections = [s for s, _ in split_sections(DOC)]
    assert sections == ["Exames", "Exames › Coleta de sangue", "Exames › Coleta de sangue › Preparo", "Exames › Resultados"]


def test_chunks_nao_misturam_secoes() -> None:
    chunks = chunk_text(DOC)
    preparo = next(c for c in chunks if c.section and c.section.endswith("Preparo"))
    assert "Glicemia" in preparo.text
    assert "Entregues" not in preparo.text


def test_paragrafos_longos_respeitam_tamanho_e_sobreposicao() -> None:
    words = " ".join(f"palavra{i}" for i in range(400))  # ~4000 caracteres, um único parágrafo
    chunks = chunk_text(f"# Título\n\n{words}")
    assert len(chunks) > 1
    assert all(len(c.text) <= CHUNK_SIZE for c in chunks)
    for prev, nxt in zip(chunks, chunks[1:]):
        first_word = nxt.text.split()[0]
        assert first_word in prev.text[-(CHUNK_OVERLAP + 20):]  # começa dentro da sobreposição
        assert not nxt.text.startswith(prev.text[:20])


def test_paragrafos_curtos_sao_agrupados_ate_o_limite() -> None:
    body = "\n\n".join(f"Parágrafo {i} " + "texto " * 20 for i in range(20))
    chunks = chunk_text(f"# Seção\n\n{body}")
    assert all(len(c.text) <= CHUNK_SIZE for c in chunks)
    assert len(chunks) < 20  # agrupou parágrafos
    assert any("Parágrafo 0" in c.text for c in chunks) and any("Parágrafo 19" in c.text for c in chunks)


def test_texto_vazio_nao_gera_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_id_deterministico() -> None:
    assert point_id("vacinas.md", 0) == point_id("vacinas.md", 0)
    assert point_id("vacinas.md", 0) != point_id("vacinas.md", 1)
    assert point_id("vacinas.md", 0) != point_id("exames.md", 0)


def test_documentos_reais_geram_chunks_validos() -> None:
    for path in DATA_DIR.glob("*.md"):
        chunks = chunk_text(path.read_text(encoding="utf-8"))
        assert chunks, path.name
        assert all(0 < len(c.text) <= CHUNK_SIZE and c.section for c in chunks)
