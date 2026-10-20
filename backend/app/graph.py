"""Grafo LangGraph do assistente (SPEC §5.1)."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.llm import message_text
from app.models import ChatTurn, GraphState, RetrievedChunk, Source
from app.prompts import GENERATE_SYSTEM, generate_user_prompt

SNIPPET_CHARS = 240


class Retriever(Protocol):
    def search(self, query: str, top_k: int) -> list[RetrievedChunk]: ...


@dataclass
class GraphDeps:
    retriever: Retriever
    chat_model: BaseChatModel
    top_k: int = 3


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


def to_sources(chunks: list[RetrievedChunk]) -> list[Source]:
    return [
        Source(source=c.source, section=c.section, snippet=c.text[:SNIPPET_CHARS].rstrip())
        for c in chunks
    ]


def build_graph(deps: GraphDeps) -> CompiledStateGraph:
    def retrieve(state: GraphState) -> dict[str, Any]:
        return {"route": "CONSULTA_RAG", "contexts": deps.retriever.search(state["message"], deps.top_k)}

    def generate(state: GraphState) -> dict[str, Any]:
        messages = [
            SystemMessage(GENERATE_SYSTEM),
            *history_messages(state.get("history", [])),
            HumanMessage(generate_user_prompt(state["message"], state["contexts"])),
        ]
        reply = message_text(deps.chat_model.invoke(messages))
        return {"reply": reply, "fallback": False, "llm_calls": state.get("llm_calls", 0) + 1}

    graph = StateGraph(GraphState)
    graph.add_node("retrieve", timed("retrieve", retrieve))
    graph.add_node("generate", timed("generate", generate))
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()
