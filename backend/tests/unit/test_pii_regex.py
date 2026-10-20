"""Camada determinística de PII (SPEC RF02.1, Apêndice C.1)."""

import pytest

from app.guardrails import PII_PATTERNS, find_pii


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("meu cpf é 123.456.789-09", "cpf"),
        ("cpf 12345678909", "cpf"),
        ("123.456.78909", "cpf"),
        ("meu cartão sus é 898 0012 3456 7890", "cns"),
        ("cns 898001234567890", "cns"),
        ("RG 12.345.678-9", "rg"),
        ("rg 1.234.567-X", "rg"),
        ("me liga no (11) 98765-4321", "telefone"),
        ("telefone 11 3456-7890", "telefone"),
        ("whats 98765-4321", "telefone"),
        ("meu email é maria.souza+ubs@exemplo.com.br", "email"),
    ],
)
def test_detecta_dados_pessoais(text: str, kind: str) -> None:
    assert find_pii(text) == kind


@pytest.mark.parametrize(
    "text",
    [
        "a vacina é das 8h às 16h",
        "dose de 0,5 ml",
        "consulta dia 12/05/2026 às 14:30",
        "meu filho tem 5 anos e pesa 20 kg",
        "a campanha vai de abril a junho de 2026",
        "jejum de 8 a 12 horas",
        "tomei 2 doses, falta a 3ª",
        "a UBS fica na Rua das Acácias, 100",
    ],
)
def test_nao_bloqueia_numeros_comuns(text: str) -> None:
    assert find_pii(text) is None


def test_padroes_sao_os_da_spec_na_ordem() -> None:
    assert list(PII_PATTERNS) == ["cpf", "cns", "rg", "telefone", "email"]
