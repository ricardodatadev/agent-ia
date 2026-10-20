"""Grafo LangGraph do assistente (SPEC §5.1)."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from app.guardrails import check_input, classify_intent, is_urgent, mentions_suicide
from app.judge import Judge
from app.llm import message_text
from app.models import ChatTurn, GraphState, Intent, RetrievedChunk, Source, ToolCallInfo
from app.prompts import (
    BLOCK_REPLIES,
    CVV_NOTICE,
    EMERGENCY_NOTICE,
    FALLBACK_REPLY,
    GENERATE_SYSTEM,
    OUT_OF_SCOPE_REPLY,
    TOOL_AGENDAMENTO_SYSTEM,
    TOOL_ATENDENTE_SYSTEM,
    generate_user_prompt,
    handoff_reply,
    schedule_ask_reply,
    schedule_confirmed_reply,
    schedule_unavailable_reply,
)
from app.tools import (
    AGENDAR_SCHEMA,
    ATENDENTE_SCHEMA,
    ESPECIALIDADES,
    NEEDS_REFERRAL,
    TOOL_AGENDAR,
    TOOL_ATENDENTE,
    AgendarConsultaArgs,
    EncaminharAtendenteArgs,
    agendar_consulta_especialista,
    encaminhar_atendente_humano,
    resolve_especialidade,
)

logger = logging.getLogger(__name__)

SNIPPET_CHARS = 240

# Próximo nó de cada intenção do Choice (SPEC RF02.2)
INTENT_NODES: dict[Intent, str] = {
    "CONSULTA_RAG": "retrieve",
    "AGENDAMENTO": "tool_agendamento",
    "ATENDIMENTO_HUMANO": "tool_atendente",
    "FORA_DO_NICHO": "resposta_fora_nicho",
}


class Retriever(Protocol):
    def search(self, query: str, top_k: int) -> list[RetrievedChunk]: ...


@dataclass
class GraphDeps:
    retriever: Retriever
    chat_model: BaseChatModel
    judge: Judge
    top_k: int = 3
    score_threshold: int = 3


Node = Callable[[GraphState], dict[str, Any]]


def timed(name: str, node: Node) -> Node:
    """Registra a latência do nó em `timings_ms` (RNF02/RNF06)."""

    def wrapper(state: GraphState) -> dict[str, Any]:
        start = time.perf_counter()
        update = node(state)
        elapsed = round((time.perf_counter() - start) * 1000, 1)
        return {**update, "timings_ms": {**state.get("timings_ms", {}), name: elapsed}}

    return wrapper


def history_messages(history: list[ChatTurn]) -> list[BaseMessage]:
    return [HumanMessage(t.content) if t.role == "user" else AIMessage(t.content) for t in history]


def extract_tool_args(model: BaseChatModel, schema: dict[str, Any], system: str, message: str) -> dict[str, Any] | None:
    """Vincula UMA tool ao LLM (permissão mínima, ADR-04) e devolve os args da chamada com o nome esperado."""
    name = schema["function"]["name"]
    response = model.bind_tools([schema]).invoke([SystemMessage(system), HumanMessage(message)])
    for call in getattr(response, "tool_calls", None) or []:
        if call.get("name") == name:  # tool calls com outro nome são ignoradas
            return call.get("args") or {}
    return None


def to_sources(chunks: list[RetrievedChunk]) -> list[Source]:
    return [
        Source(source=c.source, section=c.section, snippet=c.text[:SNIPPET_CHARS].rstrip())
        for c in chunks
    ]


def build_graph(deps: GraphDeps) -> CompiledStateGraph:
    def calls(state: GraphState, n: int) -> int:
        return state.get("llm_calls", 0) + n

    # -- triagem

    def noul(state: GraphState) -> dict[str, Any]:
        decision = check_input(state["message"], deps.judge)
        if decision.guardrail:
            # LGPD: só metadados, nunca o texto da mensagem (AC-RF02-5)
            logger.info(
                "guardrail_block",
                extra={
                    "request_id": state.get("request_id"),
                    "motivo": decision.guardrail.motivo,
                    "camada": decision.guardrail.camada,
                    "pii_type": decision.pii_type,
                    "message_len": len(state["message"]),
                },
            )
            return {"route": "BLOQUEIO", "guardrail": decision.guardrail, "llm_calls": calls(state, decision.llm_calls)}
        return {"guardrail": None, "llm_calls": calls(state, decision.llm_calls)}

    def resposta_bloqueio(state: GraphState) -> dict[str, Any]:
        reply = BLOCK_REPLIES[state["guardrail"].motivo]
        if is_urgent(state["message"]):  # bloqueada, mas relata urgência: orienta o 192 mesmo assim
            reply = f"{reply} {EMERGENCY_NOTICE}"
        return {"reply": reply}

    def choice(state: GraphState) -> dict[str, Any]:
        decision = classify_intent(state["message"], state.get("history", []), deps.judge)
        return {"route": decision.intent, "urgent": decision.urgent, "llm_calls": calls(state, decision.llm_calls)}

    def resposta_fora_nicho(state: GraphState) -> dict[str, Any]:
        return {"reply": OUT_OF_SCOPE_REPLY}

    # -- tools (respostas por template, sem geração adicional)

    def tool_agendamento(state: GraphState) -> dict[str, Any]:
        message = state["message"]
        args = extract_tool_args(deps.chat_model, AGENDAR_SCHEMA, TOOL_AGENDAMENTO_SYSTEM, message)
        extracted = str((args or {}).get("especialidade") or "")
        status, especialidade = resolve_especialidade(extracted, message)
        labels = list(ESPECIALIDADES.values())
        update: dict[str, Any] = {"llm_calls": calls(state, 1), "tool_call": None}
        if status != "ok" or especialidade is None:  # não executa a tool: pede esclarecimento
            reply = schedule_ask_reply(labels) if status == "ausente" else schedule_unavailable_reply(labels)
            return {**update, "reply": reply}

        valid = AgendarConsultaArgs(especialidade=especialidade)  # validação antes da execução
        result = agendar_consulta_especialista(valid)
        reply = schedule_confirmed_reply(ESPECIALIDADES[especialidade], result.protocolo, especialidade in NEEDS_REFERRAL)
        tool_call = ToolCallInfo(name=TOOL_AGENDAR, args=valid.model_dump(), result=result)
        return {**update, "reply": reply, "tool_call": tool_call}

    def tool_atendente(state: GraphState) -> dict[str, Any]:
        message = state["message"]
        fallback_motivo = f"Solicitação do paciente: {message}"[:200]
        if state.get("urgent"):  # urgência conhecida: encaminha sem chamar o LLM (ADR-07)
            valid = EncaminharAtendenteArgs(motivo=f"Urgência relatada: {message}"[:200], urgente=True)
            n = 0
        else:
            args = extract_tool_args(deps.chat_model, ATENDENTE_SCHEMA, TOOL_ATENDENTE_SYSTEM, message) or {}
            n = 1
            try:
                valid = EncaminharAtendenteArgs(**args)
            except (ValidationError, TypeError):  # motivo inválido não impede o encaminhamento
                valid = EncaminharAtendenteArgs(motivo=fallback_motivo, urgente=bool(args.get("urgente") is True))
        result = encaminhar_atendente_humano(valid)
        reply = handoff_reply(result.protocolo, valid.urgente)
        if mentions_suicide(message):
            reply = f"{reply} {CVV_NOTICE}"
        tool_call = ToolCallInfo(name=TOOL_ATENDENTE, args=valid.model_dump(), result=result)
        return {"reply": reply, "tool_call": tool_call, "llm_calls": calls(state, n)}

    # -- RAG

    def retrieve(state: GraphState) -> dict[str, Any]:
        return {"contexts": deps.retriever.search(state["message"], deps.top_k)}

    def score(state: GraphState) -> dict[str, Any]:
        value, n = deps.judge.score(state["message"], state["contexts"])
        return {"score": value, "llm_calls": calls(state, n)}

    def fallback(state: GraphState) -> dict[str, Any]:
        return {"reply": FALLBACK_REPLY, "fallback": True}

    def generate(state: GraphState) -> dict[str, Any]:
        messages = [
            SystemMessage(GENERATE_SYSTEM),
            *history_messages(state.get("history", [])),
            HumanMessage(generate_user_prompt(state["message"], state["contexts"])),
        ]
        reply = message_text(deps.chat_model.invoke(messages))
        return {"reply": reply, "fallback": False, "llm_calls": calls(state, 1)}

    # -- arestas condicionais

    def after_noul(state: GraphState) -> str:
        return "resposta_bloqueio" if state.get("guardrail") else "choice"

    def after_choice(state: GraphState) -> str:
        return INTENT_NODES[state["route"]]

    def after_retrieve(state: GraphState) -> str:
        return "score" if state["contexts"] else "fallback"  # sem chunks: nem chama o Score

    def after_score(state: GraphState) -> str:
        return "generate" if (state.get("score") or 0) >= deps.score_threshold else "fallback"

    nodes: dict[str, Node] = {
        "noul": noul,
        "resposta_bloqueio": resposta_bloqueio,
        "choice": choice,
        "resposta_fora_nicho": resposta_fora_nicho,
        "tool_agendamento": tool_agendamento,
        "tool_atendente": tool_atendente,
        "retrieve": retrieve,
        "score": score,
        "generate": generate,
        "fallback": fallback,
    }
    graph = StateGraph(GraphState)
    for name, node in nodes.items():
        graph.add_node(name, timed(name, node))

    graph.add_edge(START, "noul")
    graph.add_conditional_edges("noul", after_noul, ["resposta_bloqueio", "choice"])
    graph.add_conditional_edges("choice", after_choice, list(INTENT_NODES.values()))
    graph.add_conditional_edges("retrieve", after_retrieve, ["score", "fallback"])
    graph.add_conditional_edges("score", after_score, ["generate", "fallback"])
    for terminal in ("resposta_bloqueio", "resposta_fora_nicho", "tool_agendamento", "tool_atendente", "generate", "fallback"):
        graph.add_edge(terminal, END)
    return graph.compile()
