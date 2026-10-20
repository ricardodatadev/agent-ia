"""Contratos tipados da API e do estado do grafo (SPEC §5.2 e §5.3)."""

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

Route = Literal["BLOQUEIO", "CONSULTA_RAG", "AGENDAMENTO", "ATENDIMENTO_HUMANO", "FORA_DO_NICHO"]
Intent = Literal["CONSULTA_RAG", "AGENDAMENTO", "ATENDIMENTO_HUMANO", "FORA_DO_NICHO"]
BlockReason = Literal["OFENSA", "PII", "INDETERMINADO"]
GuardrailLayer = Literal["regex", "llm", "jev"]
ToolName = Literal["agendar_consulta_especialista", "encaminhar_atendente_humano"]

MAX_MESSAGE_CHARS = 1000
MAX_HISTORY = 6


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    history: list[ChatTurn] = Field(default_factory=list, max_length=MAX_HISTORY)


class GuardrailResult(BaseModel):
    motivo: BlockReason
    camada: GuardrailLayer


class ToolResult(BaseModel):
    tool: ToolName
    sucesso: bool
    protocolo: str
    mensagem: str


class ToolCallInfo(BaseModel):
    name: ToolName
    args: dict[str, Any]
    result: ToolResult


class RetrievedChunk(BaseModel):
    source: str
    section: str | None = None
    chunk_index: int
    text: str
    similarity: float = 0.0


class Source(BaseModel):
    source: str
    section: str | None = None
    snippet: str


class ChatResponse(BaseModel):
    request_id: str
    reply: str
    route: Route
    guardrail: GuardrailResult | None = None
    tool_call: ToolCallInfo | None = None
    score: int | None = None
    fallback: bool = False
    sources: list[Source] = Field(default_factory=list)


class GraphState(TypedDict, total=False):
    request_id: str
    message: str
    history: list[ChatTurn]
    route: Route
    guardrail: GuardrailResult | None
    contexts: list[RetrievedChunk]
    score: int | None
    fallback: bool
    tool_call: ToolCallInfo | None
    reply: str
    llm_calls: int
    timings_ms: dict[str, float]
