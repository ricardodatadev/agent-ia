"""API FastAPI: POST /chat e GET /health (SPEC §5.3)."""

import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.graph import GraphDeps, build_graph, to_sources
from app.llm import make_chat_model
from app.models import ChatRequest, ChatResponse, GraphState
from app.rag import VectorStore


def build_deps(settings: Settings) -> GraphDeps:
    return GraphDeps(
        retriever=VectorStore.from_settings(settings),
        chat_model=make_chat_model(settings),
        top_k=settings.top_k,
    )


def to_response(state: GraphState) -> ChatResponse:
    contexts = [] if state.get("fallback") else state.get("contexts", [])
    return ChatResponse(
        request_id=state["request_id"],
        reply=state["reply"],
        route=state["route"],
        guardrail=state.get("guardrail"),
        tool_call=state.get("tool_call"),
        score=state.get("score"),
        fallback=state.get("fallback", False),
        sources=to_sources(contexts),
    )


def create_app(settings: Settings | None = None, deps: GraphDeps | None = None) -> FastAPI:
    """`deps` permite injetar LLM/retriever falsos nos testes."""
    settings = settings or get_settings()
    graph = build_graph(deps or build_deps(settings))

    app = FastAPI(title="Assistente UBS · Agente de IA", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok"}

    @app.post("/chat", response_model=ChatResponse)
    def chat(req: ChatRequest) -> ChatResponse:
        state: GraphState = {
            "request_id": uuid.uuid4().hex,
            "message": req.message,
            "history": req.history,
            "llm_calls": 0,
            "timings_ms": {},
        }
        return to_response(graph.invoke(state))

    return app


app = create_app()
