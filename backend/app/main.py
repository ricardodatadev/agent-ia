"""API FastAPI: POST /chat e GET /health (SPEC §5.3), com logs JSON e erros 503 amigáveis (RNF05, RNF06)."""

import json
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.errors import DependencyUnavailable
from app.graph import GraphDeps, build_graph, to_sources
from app.judge import LLMJudge
from app.llm import LLM_ERRORS, make_chat_model, make_judge_model
from app.models import ChatRequest, ChatResponse, GraphState
from app.rag import VectorStore

logger = logging.getLogger("app")

UNAVAILABLE_DETAIL = "Serviço temporariamente indisponível. Tente novamente em instantes."
HEALTH_TIMEOUT_S = 5

# --------------------------------------------------------------------------- logs


class JsonFormatter(logging.Formatter):
    """Uma linha JSON por evento; campos de `extra` viram chaves do objeto."""

    _STANDARD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update({k: v for k, v in record.__dict__.items() if k not in self._STANDARD})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)  # stack só no log, nunca na resposta
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    for noisy in ("httpx", "httpx2", "httpcore"):  # registram URLs a cada chamada
        logging.getLogger(noisy).setLevel(logging.WARNING)


# --------------------------------------------------------------------------- dependências


def build_deps(settings: Settings) -> GraphDeps:
    return GraphDeps(
        retriever=VectorStore.from_settings(settings),
        chat_model=make_chat_model(settings),
        judge=LLMJudge(make_judge_model(settings)),
        top_k=settings.top_k,
        score_threshold=settings.score_threshold,
    )


HealthProbe = Callable[[], dict[str, Any]]


def make_health_probe(settings: Settings, store: VectorStore) -> HealthProbe:
    def probe() -> dict[str, Any]:
        status: dict[str, Any] = {"qdrant": "ok", "ollama": "ok", "collection_points": None}
        try:
            status["collection_points"] = store.count()
        except DependencyUnavailable:
            status["qdrant"] = "erro"
        try:
            httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=HEALTH_TIMEOUT_S).raise_for_status()
        except httpx.HTTPError:
            status["ollama"] = "erro"
        return status

    return probe


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


def request_log(state: GraphState, req: ChatRequest, total_ms: float) -> dict[str, Any]:
    """Metadados da requisição — nunca o texto das mensagens (LGPD, RNF03)."""
    guardrail = state.get("guardrail")
    tool_call = state.get("tool_call")
    return {
        "request_id": state["request_id"],
        "route": state.get("route"),
        "guardrail": guardrail.model_dump() if guardrail else None,
        "score": state.get("score"),
        "fallback": state.get("fallback", False),
        "tool": tool_call.name if tool_call else None,
        "llm_calls": state.get("llm_calls", 0),
        "timings_ms": state.get("timings_ms", {}),
        "total_ms": total_ms,
        "message_len": len(req.message),
        "history_len": len(req.history),
    }


# --------------------------------------------------------------------------- app


def create_app(
    settings: Settings | None = None,
    deps: GraphDeps | None = None,
    health_probe: HealthProbe | None = None,
) -> FastAPI:
    """`deps` e `health_probe` permitem injetar dublês nos testes."""
    configure_logging()
    settings = settings or get_settings()
    if deps is None:
        deps = build_deps(settings)
        if health_probe is None and isinstance(deps.retriever, VectorStore):
            health_probe = make_health_probe(settings, deps.retriever)
    graph = build_graph(deps)

    app = FastAPI(title="Assistente UBS · Agente de IA", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health() -> JSONResponse:
        status = health_probe() if health_probe else {}
        ok = all(v != "erro" for v in status.values())
        return JSONResponse({"status": "ok" if ok else "degradado", **status}, status_code=200 if ok else 503)

    @app.post("/chat", response_model=ChatResponse)
    def chat(req: ChatRequest) -> ChatResponse | JSONResponse:
        request_id = uuid.uuid4().hex
        state: GraphState = {
            "request_id": request_id,
            "message": req.message,
            "history": req.history,
            "llm_calls": 0,
            "timings_ms": {},
        }
        start = time.perf_counter()
        try:
            final = graph.invoke(state)
        except (DependencyUnavailable, *LLM_ERRORS) as exc:
            dependency = exc.dependency if isinstance(exc, DependencyUnavailable) else "llm"
            logger.error(
                "dependency_error",
                exc_info=True,
                extra={"request_id": request_id, "dependency": dependency, "error": type(exc).__name__},
            )
            return JSONResponse({"detail": UNAVAILABLE_DETAIL}, status_code=503)
        total_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.info("chat_request", extra=request_log(final, req, total_ms))
        return to_response(final)

    return app


app = create_app()
