"""Tools mockadas: contratos tipados, normalização de especialidade e execução (SPEC RF03, ADR-04, ADR-08)."""

import uuid
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models import ToolResult
from app.text import normalize

Especialidade = Literal[
    "clinico_geral", "pediatria", "ginecologia", "odontologia",
    "cardiologia", "dermatologia", "psicologia", "nutricao",
]

# Mesma lista de data/especialidades.md (Apêndice C.3)
ESPECIALIDADES: dict[Especialidade, str] = {
    "clinico_geral": "Clínico geral",
    "pediatria": "Pediatria",
    "ginecologia": "Ginecologia",
    "odontologia": "Odontologia (dentista)",
    "cardiologia": "Cardiologia",
    "dermatologia": "Dermatologia",
    "psicologia": "Psicologia",
    "nutricao": "Nutrição",
}

# Termos (substring do texto normalizado), avaliados na ordem da tabela: a primeira que casar vence.
ESPECIALIDADE_TERMS: dict[Especialidade, tuple[str, ...]] = {
    "clinico_geral": ("clinico", "clinica geral", "medico geral", "generalista", "clinico_geral"),
    "pediatria": ("pediatr",),
    "ginecologia": ("ginecolog", "gineco"),
    "odontologia": ("dentista", "odonto"),
    "cardiologia": ("cardio", "coracao"),
    "dermatologia": ("dermato", "pele"),
    "psicologia": ("psicolog",),
    "nutricao": ("nutri",),
}

# Primeira consulta exige avaliação do clínico geral (data/especialidades.md)
NEEDS_REFERRAL: frozenset[Especialidade] = frozenset({"cardiologia", "dermatologia", "psicologia", "nutricao"})

# O que o LLM às vezes "extrai" quando o paciente não disse especialidade nenhuma
_GENERIC_TERMS = frozenset({"", "consulta", "medico", "medica", "especialista", "doutor", "doutora", "qualquer", "nenhuma", "nao informado", "nao informada", "none", "null"})

TOOL_AGENDAR = "agendar_consulta_especialista"
TOOL_ATENDENTE = "encaminhar_atendente_humano"


class AgendarConsultaArgs(BaseModel):
    especialidade: Especialidade


class EncaminharAtendenteArgs(BaseModel):
    motivo: str = Field(min_length=3, max_length=200)
    urgente: bool = False


# Esquemas expostos ao LLM: especialidade em texto livre; a validação forte fica no código (ADR-08).
AGENDAR_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_AGENDAR,
        "description": "Solicita o agendamento de uma consulta na rede municipal de saúde.",
        "parameters": {
            "type": "object",
            "properties": {
                "especialidade": {
                    "type": "string",
                    "description": "Especialidade como o paciente escreveu (ex.: 'cardiologista', 'médico do coração'). Vazio se ele não informou.",
                }
            },
            "required": ["especialidade"],
        },
    },
}

ATENDENTE_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_ATENDENTE,
        "description": "Encaminha o paciente para a equipe de atendimento ou enfermagem da rede municipal de saúde.",
        "parameters": {
            "type": "object",
            "properties": {
                "motivo": {"type": "string", "description": "Resumo curto do motivo, em uma frase."},
                "urgente": {"type": "boolean", "description": "true se o paciente relata sintoma grave ou urgência."},
            },
            "required": ["motivo", "urgente"],
        },
    },
}


EspecialidadeLookup = tuple[Literal["ok", "ausente", "indisponivel"], Especialidade | None]


def normalize_especialidade(text: str) -> Especialidade | None:
    normalized = normalize(text)
    for canonical, terms in ESPECIALIDADE_TERMS.items():
        if any(term in normalized for term in terms):
            return canonical
    return None


def resolve_especialidade(extracted: str | None, message: str) -> EspecialidadeLookup:
    """Especialidade extraída pelo LLM ou, se ele não extraiu nada útil, a da própria mensagem."""
    for text in (extracted or "", message):
        canonical = normalize_especialidade(text)
        if canonical:
            return "ok", canonical
    extracted_norm = normalize(extracted or "").strip(" .")
    return ("ausente" if extracted_norm in _GENERIC_TERMS else "indisponivel"), None


def _protocol(prefix: str) -> str:
    return f"{prefix}-{date.today():%Y%m%d}-{uuid.uuid4().hex[:4].upper()}"


def agendar_consulta_especialista(args: AgendarConsultaArgs) -> ToolResult:
    """Mock: sem agenda real; só gera o protocolo."""
    label = ESPECIALIDADES[args.especialidade]
    return ToolResult(
        tool=TOOL_AGENDAR,
        sucesso=True,
        protocolo=_protocol("AGD"),
        mensagem=f"Solicitação de consulta de {label} registrada.",
    )


def encaminhar_atendente_humano(args: EncaminharAtendenteArgs) -> ToolResult:
    """Mock: sem fila real; só gera o protocolo."""
    return ToolResult(
        tool=TOOL_ATENDENTE,
        sucesso=True,
        protocolo=_protocol("ATD"),
        mensagem="Encaminhamento prioritário registrado." if args.urgente else "Encaminhamento registrado.",
    )
